from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
import logging
import os
import sys
import time
from enum import Enum
from logging import getLogger
from pathlib import Path
from typing import Literal, Self

import dateutil
import dateutil.parser
import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from typing_sim import TypingSim

HOME_PATH = Path(__file__).parent.resolve()
WritingMode = Literal["json", "csv"]
WRITING_MODE: WritingMode

# CONFIGURATION:
SKIP_INVALID = True
SAVING_INTERVAL_SECONDS = 1.0
WRITING_MODE = "json"  # can be "json" or "csv". json is more stable.
SAVING_PATH = HOME_PATH / "scraped"  # does not include file extension
ERROR_SCREENSHOT_PATH = HOME_PATH / "disaster.png"
# END OF CONFIG

LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s: %(message)s")
log = getLogger()

load_dotenv("./.env")
NEEDED_ENV_KEYS = {"discord_email", "discord_pass"}
OPTIONAL_ENV_KEYS = {
    "target_server_name",
    "target_channel_id"
}
for key in NEEDED_ENV_KEYS:
    if not os.getenv(key):
        log.error(f"INVALID OR MISSING .env KEY OR FILE: {key}")
        sys.exit(1)


class Codes(Enum):
    BREAK_INNER = 1
    PASS = 2


class DiscordSession:
    def __init__(self, sel: tuple[WebDriver, Options]) -> None:
        self.sel = sel

    def __enter__(self) -> Self:
        self.email, self.passkeys = self.get_keys()
        self.driver, self.options = self.sel
        self.utils = Helpers(self.driver)
        self.init_stealth()
        self.enter_discord()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> Literal[False]:
        if exc_type:
            self.utils.screenshot()
        self.driver.quit()
        return False

    def get_keys(self) -> tuple[str, str]:
        email = os.getenv("discord_email")
        keys = os.getenv("discord_pass")
        if not email or not keys:
            sys.exit(1)
        return email, keys

    def init_stealth(self) -> None:
        return stealth(
            self.driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    def enter_discord(self) -> None:
        util = self.utils
        self.driver.get("https://discord.com/login")

        email_field = util.wait_aria("Email or Phone Number")
        email_field.click()
        email_field.send_keys(self.email)

        passwd_field = util.wait_aria("Password")
        passwd_field.click()
        passwd_field.send_keys(self.passkeys)

        login_button = util.wait_css('type="submit"')
        login_button.click()


class Message:
    def __init__(
        self, message: WebElement, last_msg: dict | None, browser: WebDriver
    ) -> None:
        self.browser = browser
        self.msg_div = message
        self.last_msg = last_msg
        self.utils = Helpers(browser)
        self.is_reply_preview = self.see_if_is_reply()
        self.author_name = self.find_name()
        self.author_id = self.find_id()
        self.body = self.find_text()
        self.datetime = self.find_time()
        _temp = self.utils.get_server_and_channel()
        self.server_id, self.channel_id = _temp["server"], _temp["channel"]
        self.see_if_is_headless()
        if not self.is_reply_preview:
            log.info(f"READ MESSAGE BY {self.author_name}.")

    def see_if_is_reply(self) -> bool:
        try:
            self.msg_div.find_element(
                By.XPATH, './/div[contains(@class, "repliedTextPreview")]'
            )
            return True
        except NoSuchElementException:
            return False

    def see_if_is_headless(self) -> None:
        if self.last_msg:
            if not self.author_name and not self.author_id and self.body:
                last_id = self.last_msg.get("author_id")
                last_name = self.last_msg.get("author_name")
                if last_id and last_name:
                    self.author_id = last_id
                    self.author_name = last_name

    def find_id(self) -> str | None:
        try:
            u_id = self.msg_div.find_element(
                By.XPATH, './/span[contains(@id, "message-username-")]'
            ).get_attribute("id")
            if u_id:
                return u_id.rsplit("-", 1)[-1]
        except NoSuchElementException:
            return

    def find_name(self) -> str | None:
        try:
            return self.msg_div.find_element(
                By.XPATH,
                './/span[contains(@class, "username_") and @role="button" and text()]',
            ).text
        except NoSuchElementException:
            return

    def find_images(self, parent: WebElement) -> str:
        try:
            emoji = parent.find_element(By.XPATH, './/img[@data-type="emoji"]')
            link = emoji.get_attribute("src")
            if link:
                return f"<Emoji src={link}/>"
        except NoSuchElementException:
            pass

        try:
            imgs = parent.find_elements(
                By.XPATH,
                './/div[@data-role="img"]',
            )
            for img in imgs:
                src = img.get_attribute("src")
                if src:
                    return f'<img src="{src}"/>'
        except NoSuchElementException:
            pass

        return ""

    def find_text(self) -> str | None:
        try:
            wrapper = self.msg_div.find_element(
                By.XPATH, './/div[contains(@id, "message-content")]'
            )
            result = ""
            all_elements = wrapper.find_elements(By.XPATH, ".//*[not(self::span)]")
            spans = wrapper.find_elements(By.XPATH, ".//span")
            for elm in spans:
                result += elm.text
            for elm in all_elements:
                result += self.find_images(elm)
                if elm.tag_name == "br":
                    result += "\n"

            return result if result else None
        except NoSuchElementException:
            return

    def find_time(self) -> str | None:
        try:
            return self.msg_div.find_element(
                By.XPATH,
                ".//time[@datetime]",
            ).get_attribute("datetime")
        except NoSuchElementException:
            return

    def to_dict(self) -> dict[str, str | None | bool]:
        return {
            "author_name": self.author_name,
            "author_id": self.author_id,
            "body": self.body,
            "time": self.datetime,
            "server_id": self.server_id,
            "channel_id": self.channel_id,
            "is_reply_preview": self.is_reply_preview,
        }


class MessageScrape:
    def __init__(self, driver: WebDriver) -> None:
        self.server = None
        self.driver = driver
        self.utils = Helpers(driver)
        self.enter_server()
        if c_id := os.getenv("target_channel_id"):
            self.driver.get(
                f"https://discord.com/channels/{self.get_server_id()}/{c_id}"
            )
        self.saving_file = Path(str(SAVING_PATH) + f".{WRITING_MODE}")
        self.last_check = datetime.now().timestamp()
        self.is_crazy = os.getenv("crazy") or True
        if isinstance(self.is_crazy, str):
            self.is_crazy = True if self.is_crazy.lower().strip()\
                in ["true", "yes", "y"] else False
        self.saved_messages = self.load_logs()
        scraped = self.scrape_messages(self.saved_messages)
        if scraped:
            self.save_logs(scraped)

    def get_server_id(self) -> str:
        return self.driver.current_url.rstrip("/").split("/")[-2]

    def find_target_server(
        self, servers: list[WebElement]
    ) -> tuple[str, WebElement] | None:
        log.info("FOUND SERVERS.")
        target = os.getenv("target_server_name").lower()  # type: ignore
        found_target = None
        for server in servers:
            name = server.find_element(By.XPATH, ".//span").text.lower()
            found_target = (name, server) if name == target else found_target
            log.info(f"FOUND SERVER: {name}, IS TARGET: {name == target}")
            if name == target:
                return found_target
        return None

    def enter_server(self) -> None:
        if os.getenv("target_server_name"):
            server_div = self.utils.wait_aria("Servers")
            servers = server_div.find_elements(By.XPATH, './/*[@tabindex="-1"]')
            if servers:
                maybe_target = self.find_target_server(servers)
                if maybe_target:
                    log.info(f"ENTERING SERVER: {maybe_target[0]}")
                    self.server = maybe_target[0]
                    maybe_target[1].click()
                else:
                    log.error("TARGET SERVER NOT FOUND. EXITING...")
                    sys.exit(1)
            else:
                log.error("NO SERVERS FOUND IN DISCORD. EXITING...")
                sys.exit(1)
        else:
            # wait until the chatbox is visible by user intervention
            self.utils.wait_css('data-list-id="chat-messages"')

    def retrieve_messages(
        self,
        message_box: WebElement,
        seen_ids: set[str],
        logged_messages: list[dict],
    ) -> Codes | list[dict]:
        try:
            current_messages = message_box.find_elements(
                By.XPATH, './/li[contains(@class, "messageListItem")]'
            )
            for msg in current_messages:
                m_id = msg.get_attribute("id")
                if m_id in seen_ids:
                    continue
                if m_id:
                    seen_ids.add(m_id)
                last_message = None
                if len(logged_messages) > 0:
                    last_message = logged_messages[-1]
                msg = Message(msg, last_message, self.driver)
                logged_messages.append(msg.to_dict())
                if self.is_crazy and msg.body and "crazy" in msg.body.lower():
                    if msg.datetime:
                        msgdate = dateutil.parser.isoparse(msg.datetime)
                        if msgdate.timestamp() > self.last_check:
                            self.crazy()

            self.last_check = datetime.now().timestamp()
            time.sleep(SAVING_INTERVAL_SECONDS)
        except StaleElementReferenceException:
            log.warning("FAILED TO GET A MESSAGE. RE-GRABBING TEXT-BOX...")
            return Codes.BREAK_INNER
        return Codes.PASS

    def scrape_messages(self, messages: list[dict]) -> list[dict]:
        while True:
            message_box = self.utils.wait_css('data-list-id="chat-messages"')
            ids = set()
            log.info("BEGINNING TO SCRAPE. TO EXIT, PRESS CTRL+C.")
            while True:
                try:
                    maybe_messages = self.retrieve_messages(message_box, ids, messages)
                    if maybe_messages == Codes.BREAK_INNER:
                        break
                except KeyboardInterrupt:
                    return messages

    def crazy(self):
        textbox = self.driver.find_element(
            By.XPATH, "//div[@role=\"textbox\"" +
            " and @contenteditable=\"true\"]"
        )
        while "Pigs don't fly":
            for sentence in CRAZY:
                typer = TypingSim(sentence)
                textbox.click()
                for c in typer:
                    if self.driver.switch_to.active_element != textbox:
                        print("sorry :( ")
                        return
                    textbox.send_keys(c)
                # in case of slowmode
                while textbox.text:
                    if self.driver.switch_to.active_element != textbox:
                        print("sorry :( ")
                        return
                    textbox.send_keys("\n") # enter
                    if textbox.text:
                        time.sleep(0.5)

    def write_csv(self, file: Path, to_write: str) -> None:
        csv = pd.read_json(StringIO(to_write), encoding="utf-8").to_csv(
            encoding="utf-8", index=False
        )
        file.write_text(csv, "utf-8")

    def load_logs(self) -> list[dict]:
        return self.utils.check_json(self.saving_file)

    def to_dict(self, messages: list[Message]) -> list[dict]:
        return list(map(lambda m: m.to_dict(), messages))

    def filter_logs(self, msglist: list[dict]) -> list[dict]:
        seen = set()
        unique_logs = []
        for entry in msglist:
            entry = self.remove_previews(entry)
            if not entry:
                continue
            if SKIP_INVALID and not all(entry.values()):
                continue
            key = (entry.get("author_id"), entry.get("time"))
            if key not in seen and not entry.get("is_reply_preview"):
                seen.add(key)
                unique_logs.append(entry)
        return unique_logs

    def write_logs(self, file: Path, to_save: list[dict]) -> None:
        if to_save:
            logs = json.dumps(to_save)
            if WRITING_MODE == "csv":
                self.write_csv(file, logs)
            else:
                file.write_text(logs, "utf-8")

    def save_logs(self, messages: list[dict]) -> None:
        unique = self.filter_logs(messages)
        self.write_logs(self.saving_file, unique)

    def remove_previews(self, msg: dict[str, str | bool | None]):
        if msg.get("is_reply_preview"):
            return None
        msg.pop("is_reply_preview", None)
        return msg

# hidden!
CRAZY = ["Crazy?", "I was crazy once.", "They put me in a room.",
         "A rubber room.", "A rubber room with rats.", "A rubber" +
         " room with rubber rats.", "Rubber rats? I hate rubber " +
         "rats.", "They make me crazy."]

class Helpers:
    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self.waiter = WebDriverWait(self.driver, 100)

    def wait_aria(self, aria: str) -> WebElement:
        return self.wait_css(f'aria-label="{aria}"')

    def get_server_and_channel(self) -> dict[str, str]:
        url_parts = self.driver.current_url.removesuffix("/").split("/")[-2:]
        return {"server": url_parts[0], "channel": url_parts[1]}

    def wait_css(self, css_selector: str) -> WebElement:
        return self.wait_any(By.CSS_SELECTOR, f"[{css_selector}]")

    def wait_any(self, by: str, select: str) -> WebElement:
        return self.waiter.until(EC.visibility_of_element_located((by, select)))

    @staticmethod
    def check_json(file: Path) -> list[dict]:
        if file.exists():
            text = file.read_text("utf-8")
            if len(text) > 3:
                if WRITING_MODE == "json":
                    error = False
                    try:
                        old = json.loads(text)
                        if not isinstance(old, list):
                            error = True
                    except json.decoder.JSONDecodeError:
                        old = []
                        error = True
                    if error or not old:
                        log.error(
                            f"ERROR: INVALID {file.name} FILE. PARSING ERROR. RENAMING..."
                        )
                        file.rename(file.parent / f"invalidJSON-{time.time()}.json")
                        return []
                    return old
                else:
                    return pd.read_csv(file, encoding="utf-8").to_dict(orient="records")
        return []

    @staticmethod
    def init_sel() -> tuple[WebDriver, Options]:
        options = webdriver.ChromeOptions()
        options.add_argument("start-maximized")
        options.add_argument("--log-level=3")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        driver = webdriver.Chrome(options)
        return driver, options

    def screenshot(self) -> None:
        original_size = self.driver.get_window_size()
        full_width = self.driver.execute_script(
            "return document.body.parentNode.scrollWidth"
        )
        full_height = self.driver.execute_script(
            "return document.body.parentNode.scrollHeight"
        )
        self.driver.set_window_size(full_width, full_height)
        self.driver.save_screenshot(str(ERROR_SCREENSHOT_PATH))
        self.driver.set_window_size(original_size["width"], original_size["height"])


def init() -> None:
    sel = Helpers.init_sel()
    with DiscordSession(sel):
        log.info("SUCCESSFULLY LOGGED ON.")
        MessageScrape(sel[0])
        log.info("FINISHED SCRAPING. CLOSING BROWSER...")
    log.info("PROGRAM FINISHED RUNNING.")

if __name__ == "__main__":
    init()
