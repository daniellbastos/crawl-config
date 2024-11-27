import os
import json
import logging

from datetime import datetime
from time import sleep

from playwright.sync_api import expect, sync_playwright, TimeoutError as PlaywrightTimeoutErrort

from undetected_playwright import stealth_sync

logger = logging.getLogger(__name__)


def take_fail_screenshot(func):
    def wrapper(*args, **kwargs):
        try:
            print("take_fail_screenshot", f"args={args}, kwargs={kwargs}")
            return func(*args, **kwargs)
        except Exception as exc:
            logger.warning("take_fail_screenshot", f"raised exception {exc}")
            data = args[0]

            str_now = datetime.now().strftime("%Y%m%d%H%M%S")
            output_dir = data.get("output_dir", None)
            if popup := data.get("popup", None):
                if output_dir:
                    popup.screenshot(path=f"{output_dir}{str_now}_popup_exception.png", full_page=True)
                popup.close()

            if output_dir:
                data["page"].screenshot(path=f"{output_dir}{str_now}_exception.png", full_page=True)
            data["page"].close()
            data["browser_context"].clear_cookies()
            raise exc

    return wrapper


def _log(filename, page, context):
    if not context.get("log", False):
        print("_log", f"filename {filename} deactivated")
        return

    print("_log", f"filename {filename}")
    output_dir = context.get('output_dir', None)
    if not output_dir:
        return

    page.screenshot(path=f'{output_dir}{filename}.png', full_page=True)
    with open(f'{output_dir}{filename}.html', 'w') as f:
        f.write(page.content())


def _solve_recaptcha_v2(context):
    print("_solve_recaptcha_v2", "start")
    solver = recaptchaV3Proxyless()
    solver.set_verbose(1)
    solver.set_key(context["anticaptcha_key"])
    solver.set_website_url(context['url'])
    solver.set_website_key(context['recaptcha_site_key'])
    solver.set_page_action("home_page")
    solver.set_min_score(0.9)
    solver.set_soft_id(0)
    recaptcha_token = solver.solve_and_return_solution()
    if recaptcha_token != 0:
        recaptcha_token = recaptcha_token
        return recaptcha_token
    else:
        logger.warning("_solve_recaptcha_v2", f"task finished with error: {solver.error_code}")
        return None


def _solve_imagecaptcha(i, step, page, context):
    if not step.get('imagecaptcha', False):
        return

    print(f"_solve_imagecaptcha {i}", "start")
    if not expect(page.get_by_text('What code is in the image?')).to_be_visible():
        logger.warning(f"_solve_imagecaptcha {i}", "'What code is in the image?' not found")
        return

    solver = imagecaptcha()
    solver.set_verbose(1)
    solver.set_key(context["anticaptcha_key"])
    solver.set_soft_id(0)
    token = solver.solve_and_return_solution('image.png')
    page_field = page.locator('input[id="ans"]')
    page_field.type(token)

    page_button = page.locator('button[type="button"]')
    page_button.click()


def _start_browser(playwright, context, headless=True):
    print("_start_browser", f"start headless={headless}")

    chrome_kwargs = {
        "headless": headless,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    user_data_dir = f"/tmp/data_dir_{datetime.now().isoformat()}_{context['id']}"

    if path_to_extension := context.get("pathc_capctcha_extension", ""):
        chrome_kwargs["args"] = [
            f"--disable-extensions-except={path_to_extension}",
            f"--load-extension={path_to_extension}",
        ]

    # Ignore presistent context for now until we find a way to resolve issues
    # when we open the browser already logged.
    # Issue: MAYBE we could to have problems when we run with two accounts at
    # the same time
    browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir,
        **chrome_kwargs
    )
    browser_context.clear_cookies()
    context['browser_context'] = browser_context
    stealth_sync(context['browser_context'])

    page = context['browser_context'].new_page()
    print("_start_browser", f"chomium page created {chrome_kwargs}")
    return page


def _run_step_navigation(i, step, page, context):
    if step["type"] != "navigation":
        return

    url = step["url"]
    print(f"_run_step_navigation {i}", f"start navigation to: '{url}'")

    page.goto(url)
    page.wait_for_load_state("load")


def _run_step_check_element(i, step, page, context):
    """
    element json format:
    {
        "element": {
            "value": "Bem-vindo",
            "extras": {
                "exact": true
            },
            "method": "<get_by_text|>"
        },
        "rollback": "<step_key>",  # will override the "normal" next_step
        "attempts": <int>,
        "reload": <bool|default is false>,  # just reload the page and check the elment again
        "goto": "<url|default is empty>"  # navigate to URL instead to reload or move to next step
    }
    """
    if step["type"] != "check_element":
        return

    print(f"_run_step_check_element {i}", "start")

    for item in step["elements"]:
        try:
            element_data = item["element"]
            element = getattr(page, element_data["method"])(element_data["value"], **element_data.get("extras", {}))

            if not element.is_visible():
                logger.warning(f"_run_step_check_element {i}", f"element not found, step data={step}")

                if "rollback" in item:
                    if item["attempts"] > 0:
                        item["attempts"] -= 1
                        item["next_item"] = item["rollback"]
                        if item.get("reload", False):
                            page.reload()
                        if url := item.get("goto", ""):
                            page.goto(url)

                        sleep(2)  # TODO
        except Exception as exc:
            logger.error(f"_run_step_check_element {i}", f"exception raised: {exc}")


def _run_step_extract_content(i, step, page, context):
    """
    step json format:
    step: {
      "id": 5,
      "type": "extract_content",
      "contents": [
        {
          "element": {
            "value": "<xpath|ID|...>",
            "method": "locator"
          },
          "element_action": {
            "method": "inner_html"
          }
        }
      ],
      "target": {
        "filename": "./out/filename.html"
      },
      "next_step": "00waitfinal"
    }
    """
    if step["type"] != "extract_content":
        return

    print(f"_run_step_extract_content {i}", "start")
    output_contents = []
    for item in step["contents"]:
        element_data = item["element"]
        element_action_data = item["element_action"]
        # get the element
        # element = page.<element_data.method>(<element_data.value>, **<element_data.extras|{}>)
        element = getattr(page, element_data["method"])(element_data["value"], **element_data.get("extras", {}))
        # execute the action
        # element_action = element.<element_action_data.method|click|type>
        # element_action(**<element_action.extras|{}>)
        # element_action(<element_action_data.value>, **<element_action.extras|{}>)
        element_action = getattr(element, element_action_data["method"])

        extras = element_action_data.get("extras", {})
        extracted_content = None
        if "value" in element_action_data:
            extracted_content = element_action(element_action_data["value"], **extras)
        else:
            extracted_content = element_action(**extras)

        if extracted_content:
            output_contents.append(extracted_content)

    if not output_contents:
        raise Exception("has no extracted content")

    data = {
        "step_id": i,
        "id": context["id"],
        "output_contents": output_contents
    }
    print(f"_run_step_extract_content {i}", f"data={data}")


def _run_step_form(i, step, page, context):
    if step["type"] != "form":
        return

    print(f"_run_step_form {i}", "start")
    for field in step["form"]:
        __process_click_and_form_item(field, page)


def _run_step_captcha(i, step, page, context):
    if step["type"] != "solver_captcha":
        return

    print(f"_run_step_captcha {i}", "start")
    if step.get("recaptchav2", False):
        recaptcha_token = _solve_recaptcha_v2(context)
        try:
            if page.query_selector("#recaptchaToken"):
                page.evaluate(f"() => document.getElementById('recaptchaToken').value = '{recaptcha_token}'")
            if page.query_selector("#g-recaptcha-response"):
                page.evaluate(f"() => document.getElementById('g-recaptcha-response').value = '{recaptcha_token}'")
            if page.query_selector("#recaptcha-token"):
                page.evaluate(f"() => document.getElementById('recaptcha-token').value = '{recaptcha_token}'")
            else:
                raise Exception("selectors didn't work: #recaptcha-token, #g-recaptcha-response, #recaptchaToken")
        except Exception as exc:
            logger.warning(f"_run_step_captcha {i}", f"error: {exc}")


def __process_click_and_form_item(item, page):
    """
    element json format:
    {
        "optional": false,
        "element": {
            "value": "Accept All Cookies",
            "extras": {
                "exact": true
            },
            "method": "<get_by_text|>"
        },
        "element_action": {
            "method": "<click|>"
            "value": "<optional>",
        }
    }
    attachament field
    {
        "is_attachment": true,
        "element": {
            "value": "Accept All Cookies",
            "extras": {
                "exact": true
            },
            "method": "<get_by_text|>"
        },
        "element_action": {
            "method": "set_input_files",
            "extras": {
                "files": [{
                    "buffer": "base64-string",
                    "name": "<filename>",
                    "mimeType": "<application/pdf|...>"
                }]
            }
        }
    }

    """
    element_data = item["element"]
    element_action_data = item["element_action"]

    # get the element
    # element = page.<element_data.method>(<element_data.value>, **<element_data.extras|{}>)
    element = getattr(page, element_data["method"])(element_data["value"], **element_data.get("extras", {}))

    # execute the action
    # element_action = element.<element_action_data.method|click|type>
    # element_action(**<element_action.extras|{}>)
    # element_action(<element_action_data.value>, **<element_action.extras|{}>)
    element_action = getattr(element, element_action_data["method"])

    extras = element_action_data.get("extras", {})
    if element_action_data.get("is_attachment", False):
        files = []
        for file in extras.get("files", []):
            buffer_bytes = file["buffer"].encode()
            file["buffer"] = buffer_bytes
            files.append(file)
        extras["files"] = files

    if "value" in element_action_data:
        element_action(element_action_data["value"], **extras)
    else:
        element_action(**extras)


def _run_step_click(i, step, page, context):
    if step["type"] != "click":
        return

    print(f"_run_step_click {i}", "start")
    for iclick, field in enumerate(step["clicks"]):
        try:
            __process_click_and_form_item(field, page)
        except PlaywrightTimeoutErrort as exc:
            if field.get("optional", False):
                logger.warning(f"_run_step_click {iclick}", "element not found and skipped by optional")
                continue

            raise exc


def _run_step_wait_for(i, step, page, context):
    """
    step: {
      "id": 1,
      "time": 100,
      "type": "sleep"
    }
    """
    if step["type"] != "wait_for":
        return

    print(f"_run_step_wait_for {i}", "start")
    for item in step["elements"]:
        try:
            element_data = item["element"]
            element = getattr(page, element_data["method"])(element_data["value"], **element_data.get("extras", {}))
            element.wait_for()

        except Exception as exc:
            logger.error(f"_run_step_wait_for {i}", f"exception raised: {exc}")


    page.wait_for_load_state("load")


def _run_wait(i, step, page, context):
    print(f"_run_wait {i}", "start")
    page.wait_for_load_state("load")


def _run_step_sleep(i, step, page, context):
    if step["type"] != "sleep":
        return

    sleep_time = step["time"]
    print(f"_run_step_sleep {i}", f"start - sleep time: {sleep_time}")

    sleep(sleep_time)


def _run_step_store_url(i, step, page, context):
    if step["type"] != "store_url":
        return

    data =  {
        "step_id": i,
        "object_id": context["id"],
        "output_contents": page.url
    }
    print(f"_run_step_store_url {i}", f"data={data}")


def _route_intercept(route):
    if route.request.resource_type == "image":
        logger.debug(f"Blocking the image request to: {route.request.url}")
        return route.abort()

    return route.continue_()


def store_cookies(context):
    cookies = context['browser_context'].cookies()
    for cook in cookies:
        context['cookies'].update(cook)


def _run_step_download_page(i, step, page, context):
    if step["type"] != "download_page":
        return

    filename = step["filename"]
    print(f"_run_step_download_page {i}", f"URL={page.url}, filename={filename}")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(page.content())


def _execute_step(step, page, context, current_step=None) -> str:
    i = step.get("id", "id-undefined")
    print(f"_execute_step {i}", "start")

    page = context["page"] if not step.get("in_popup", False) else context["popup"]
    if step.get("create_popup", False):
        with page.expect_popup() as popup:
            _run_step_store_url(i, step, page, context)
            _run_step_wait_for(i, step, page, context)
            _run_step_sleep(i, step, page, context)
            _run_step_navigation(i, step, page, context)
            _run_step_check_element(i, step, page, context)
            _run_step_captcha(i, step, page, context)
            _run_step_form(i, step, page, context)
            _run_step_click(i, step, page, context)
            _run_step_extract_content(i, step, page, context)
            _run_step_download_page(i, step, page, context)

        context["popup"] = popup.value

        print(f"_execute_step {i}", "popup created")

        store_cookies(context)
        _log(current_step if current_step else f"step{i}_{step['type']}", page, context)
        return step.get("next_step", None)

    _run_step_store_url(i, step, page, context)
    _run_step_wait_for(i, step, page, context)
    _run_step_sleep(i, step, page, context)
    _run_step_navigation(i, step, page, context)
    _run_step_check_element(i, step, page, context)
    _run_step_captcha(i, step, page, context)
    _run_step_form(i, step, page, context)
    _run_step_click(i, step, page, context)
    _run_step_extract_content(i, step, page, context)
    _run_step_download_page(i, step, page, context)

    store_cookies(context)
    _log(current_step if current_step else f"step{i}_{step['type']}", page, context)
    return step.get("next_step", None)


# @take_fail_screenshot
def run(data, headless=True):
    print("run", f"start headless={headless} data={data}")

    now = datetime.now().strftime("%Y%m%d%H%M%S")
    context = {
        "id": f"{now}",
        "requests": [],
        "recaptcha_anchor_url": "",
        "browser_context": None,
        "cookies": {},
        "popup": None,
    }
    with sync_playwright() as playwright:
        context["url"] = data["url"]
        context["log"] = data.get("log", False)
        context["recaptcha_site_key"] = data.get("recaptcha_site_key", None)
        context["recaptcha_anchor_url"] = data.get("recaptcha_anchor_url", None)
        context["solver_captcha"] = data.get("solver_captcha", None)
        context["all_steps"] = data["steps"]

        if context["log"]:
            output_dir = f"./tmp/{context['id']}/"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                context["output_dir"] = output_dir

        page = _start_browser(playwright, context, headless)

        page.goto(data["url"], timeout=0)
        context["page"] = page
        store_cookies(context)

        # use on take_fail_screenshot
        next_step = data["first_step"]

        print("run", f"first step {next_step}")
        step = data["steps"][next_step]
        while step:
            next_step = _execute_step(step, page, context, current_step=next_step)
            if not next_step:
                break

            print("run", f"next step {next_step}")
            step = context["all_steps"][next_step]

        if popup := context["popup"]:
            print("run", "closing popup page")
            popup.close()

        print("run", "closing page")
        page.close()

    print("run", f"finished task")
