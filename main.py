import os
import sys, getopt
import pickle
import logging
import datetime
import inspect
from time import gmtime, strftime, sleep
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webelement import WebElement
from contextlib import contextmanager


def help():
    print(
        '''Arguments:
        -h: Help
        -d: enable debug mode
        -f: disable file logging (enabled by default)
        -n: enable headless mode (disabled by default)
        -t: enable trace mode
        -D: dry run
        '''
    )
    sys.exit()

def initConfigClass(config):
    try:
        opts, _ = getopt.getopt(sys.argv[1:], 'hdfntD')
    except:
        print('Warning: argument error!')
        sys.exit(1)
    for opt, _ in opts:
        if opt == '-h':
            help()
        elif opt == '-d':
            config.DEBUG = True
        elif opt == '-f':
            config.disableFileLogging = True
        elif opt == '-n':
            config.HEADLESS = True
        elif opt == '-t':
            config.TRACE = True
        elif opt == '-D':
            config.DRYRUN = True

    from env import text_username, text_password, cookie_name
    config.text_username = text_username
    config.text_password = text_password
    config.cookie_name = cookie_name

    config.init_logger()
    return config

@initConfigClass
class Config:

    DEBUG = False
    TRACE = False
    DRYRUN = False
    HEADLESS = False

    LOGGING_PATH = 'log'
    WAIT_TIMEOUT = 5
    configs = {
        "POP_MODAL": ".shopee-popup__close-btn",
        "AVATAR": ".shopee-avatar",
        "NAV_LOGIN_MODAL": ".navbar__link--account",
        "LOGIN_SUBMIT": "#modal > aside > div > div > div > div > div > div > button:nth-child(2)",
        "SMS_MODAL": ".shopee-authen__outline-button",
        "SMS_TEXT": ".shopee-authen .input-with-status__input",
        "SMS_SUBMIT": ".shopee-authen .btn-solid-primary",
        "LOGIN_FAILED": ".shopee-authen .shopee-authen__error",
        "COIN_PAGE_READY": ".check-box",
        "COIN_NOW": ".check-box .total-coins",
        "GET_COIN": ".check-box .check-in-tip",
        "COIN_REGULAR": ".check-box .top-btn.Regular",

        "COIN_VALUE": "p._37aS8q",
        "COIN_BUTTON": "button._1Puh5H",

        "LOGIN_USER": "loginKey",
        "LOGIN_PASS": "password",

        "HOME_URL": "https://shopee.tw",
        "COIN_PAGE": "https://shopee.tw/shopee-coins"
    }
    path = os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def get(cls, name):
        return cls.configs.get(name)

    text_username = None
    text_password = None
    cookie_name = None

    logger = None
    disableFileLogging = False

    @classmethod
    def init_logger(cls, name=None):
        log_dir   = cls.LOGGING_PATH
        log_file  = "{}/{}".format(log_dir, datetime.datetime.now().strftime("shopee.%Y-%m.log"))
        log_level = logging.DEBUG if cls.DEBUG else logging.INFO

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        logger = logging.getLogger(name)

        logger.setLevel(log_level)

        ch = logging.StreamHandler()
        formatter = logging.Formatter('[%(filename)s:%(lineno)s - %(funcName)20s() ] %(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        ch.setFormatter(formatter)

        logger.addHandler(ch)

        if not cls.disableFileLogging:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        cls.logger = logger


def discardArgSelf(args):
    _, *realargs = args # discard the first argument 'self'
    # realargs is a list not a tuple, TODO: beautify the case of single element
    return tuple(realargs)

def printCaller(callerFrame, callingStr, printer):
    caller = callerFrame.f_code.co_name
    lineno = callerFrame.f_lineno
    printer(f'{caller}:{lineno} {callingStr}')

from functools import wraps

def traceMethod(printer=print):
    def decorator(function):
        if not Config.TRACE: return function
        @wraps(function)
        def wrapper(*args, **kwargs):
            result = function(*args, **kwargs)
            caller = inspect.currentframe().f_back
            realargs = discardArgSelf(args)
            printCaller(caller, f'{function.__qualname__}{realargs} returned {result}', printer)
            return result
        return wrapper
    return decorator

def dryrunMethod(result=None):
    def decorator(function):
        if not Config.DRYRUN: return function
        @wraps(function)
        def wrapper(*args, **kwargs):
            caller = inspect.currentframe().f_back
            realargs = discardArgSelf(args)
            printCaller(caller, f'{function.__qualname__}{realargs} run dry, pretended {result}', print)
            return result
        return wrapper
    return decorator


class Driver(webdriver.Chrome):

    logger = Config.logger

    def __init__(self, width, height, headless=True):

        chrome_options = Options()
        if headless:
            # Hide the browser window
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('disable-infobars')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
        super().__init__('chromedriver',options=chrome_options)
        self.set_window_size(width, height)
        self.logger.debug("Init driver done.")

    def preloadCookie(self, cookieFile):
        with open(cookieFile, 'rb') as filehandler:
            # Enables network tracking so we may use Network.setCookie method
            self.execute_cdp_cmd('Network.enable', {})

            for cookie in pickle.load(filehandler):
                # Fix issue Chrome exports 'expiry' key but expects 'expire' on import
                if 'expiry' in cookie:
                    cookie['expires'] = cookie['expiry']
                    del cookie['expiry']
                # Set the actual cookie
                self.execute_cdp_cmd('Network.setCookie', cookie)

            # Disable network tracking
            self.execute_cdp_cmd('Network.disable', {})


    def saveCookie(self, cookieFile):
        with open(cookieFile, 'wb') as filehandler:
            pickle.dump(self.get_cookies(), filehandler)

    def loadCookie(self, cookieFile):
        with open(cookieFile, 'rb') as filehandler:
            for cookie in pickle.load(filehandler):
                self.add_cookie(cookie)

    @traceMethod()
    def waitElementPresence(self, locator, timeout=5):
        try:
            element = WebDriverWait(self, timeout).until(
                EC.presence_of_element_located(locator)
            )
            if isinstance(element, WebElement):
                self.logger.debug( f'"{repr(locator)}" located! text "{element.text}"' )
                return element

        except TimeoutException:
            self.logger.info( f'"{repr(locator)}" not located!' )

        except Exception as e:
            self.logger.error(repr(e))

        return False


class Crawler:

    config = Config
    logger = Config.logger

    def __init__(self):
        headless = (not self.config.DEBUG) or (self.config.path == '/code')
        self.driver = Driver(1200, 800, headless)

    @dryrunMethod({'success': 0, 'value': None, 'sessionId': None})
    @traceMethod() # or traceMethod(logger.info)
    def getURL(self, name):
        return self.driver.get(self.config.get(name))

    @traceMethod()
    def waitForClass(self, name):
        return self.driver.waitElementPresence((By.CSS_SELECTOR, self.config.get(name)), self.config.WAIT_TIMEOUT)

    @traceMethod()
    def getByClass(self, name):
        return self.driver.find_element_by_css_selector(self.config.get(name))

    def getByName(self, name):
        return self.driver.find_element_by_name(self.config.get(name))

    def getAllByClass(self, name):
        return self.driver.find_elements_by_css_selector(self.config.get(name))

    def getAllByName(self, name):
        return self.driver.find_elements_by_name(self.config.get(name))

    def checkPopModal(self):
        try:
            sleep(3)
            pop = self.getByClass("POP_MODAL")
            pop.click()
            self.logger.info("pop modal close")
        except :
            self.logger.info("pop modal not found")

    def checkLogin(self):
        try:
            self.waitForClass("AVATAR")
            self.logger.info("Login Success")
            return True
        except:
            self.logger.info("Login Failed")
            return False

    def loginByCookie(self):
        try:
            self.driver.loadCookie(self.config.cookie_name)
            self.driver.refresh()
            self.logger.debug(f'Use {self.config.cookie_name} to login!')
        except:
            self.logger.info(f'{self.config.cookie_name} not found!')

    def preloadCookie(self):
        try:
            self.driver.preloadCookie(self.config.cookie_name)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to load cookie from "{self.config.cookie_name}"!')

    def loadCookie(self):
        try:
            self.driver.loadCookie(self.config.cookie_name)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to load cookie from "{self.config.cookie_name}"!')

    def saveCookie(self):
        try:
            self.driver.saveCookie(self.config.cookie_name)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to save cookie to "{self.config.cookie_name}"!')

    def loginByPass(self):
        try:
            # click to show login modal
            login_button = self.getAllByClass("NAV_LOGIN_MODAL")[1]
            login_button.click()
            self.waitForClass("LOGIN_SUBMIT")
        except Exception as e:
            self.logger.error("Login Modal not showing"+repr(e))
            self.close()
        try:
            # Enter Account & Password
            accountText = self.getByName("LOGIN_USER")
            passwordText = self.getByName("LOGIN_PASS")
            submitButtom = self.getByClass("LOGIN_SUBMIT")

            accountText.send_keys(self.config.text_username)
            passwordText.send_keys(self.config.text_password)
            submitButtom.click()
            self.logger.info("Use password to login")
        except Exception as e:
            self.logger.error("Wrong account and password"+repr(e))
            self.close()
            sys.exit(0)

    def checkSMS(self):
        try:
            # Check SMS textbox exists
            self.waitForClass("SMS_MODAL")
            # Catch text & submit buttom
            smsText = self.getByClass("SMS_TEXT")
            smsSubmit = self.getByClass("SMS_SUBMIT")

            text_sms = input("Please Enter SMS code in 60 seconds: ")
            smsText.clear()
            smsText.send_keys(text_sms)
            smsSubmit.click()
            # handle sms error
            try:
                # wait to check if login success
                self.waitForClass("AVATAR")
            except:
                #login failed
                smsError = self.getByClass("LOGIN_FAILED")
                if smsError:
                    self.logger.error("Sending SMS code "+smsError.text)
                else:
                    self.logger.error("Sending SMS code Run time out.")
                self.close()
                sys.exit(0)
        except Exception as e:
            self.logger.info("No need SMS authenticate"+repr(e))

    def clickCoin(self):
        try:
            # wait for page loading
            self.getURL("COIN_PAGE")
            self.waitForClass("COIN_PAGE_READY")
            try:
                self.waitForClass("GET_COIN")
                # get information
                current_coin = self.getByClass("COIN_NOW")
                get_coin = self.getByClass("GET_COIN")
                #show before information
                self.logger.info("目前有：" + current_coin.text + " 蝦幣，" + get_coin.text)
                #click to get shopee coin
                get_coin.click()
            except:
                # Already click
                self.logger.info("今天已經獲取過蝦幣")
            #wait for already information display login-check-btn
            self.waitForClass("COIN_REGULAR")
            #show after information
            current_coin = self.getByClass("COIN_NOW")
            coin_regular = self.getByClass("COIN_REGULAR")
            self.logger.info("目前有：" + current_coin.text + " 蝦幣，" + coin_regular.text)
        except Exception as e:
            self.logger.error(repr(e))
            self.close()

    def run(self):
        self.getURL("HOME_URL")
        self.checkPopModal()
        #Use cookie to login
        self.loginByCookie()
        if not self.checkLogin():
            #Use pass to login
            self.loginByPass()
            if not self.checkLogin():
                self.checkSMS()
                if not self.checkLogin():
                    #Login failed
                    self.close()
        #After login, Go to coin page
        self.saveCookie()
        self.clickCoin()
        self.close()

    def close(self):
        self.driver.close()
        self.logger.info("Program exit")
        sys.exit(0)


class ShopeeWeb(Crawler):

    def __init__(self):
        self.driver = Driver(1200, 800, self.config.HEADLESS)

    @traceMethod() # Crawler.logger.info
    def waitLogin(self):
        return bool(self.waitForClass("AVATAR"))

    def login(self):
        ''' login by cookie or manually
        '''
        self.preloadCookie()
        self.getURL("COIN_PAGE")
        coin_button = self.waitForClass("COIN_BUTTON")
        if not coin_button:
            self.logger.info("Page loading error!")
            return False
        if '登入' in coin_button.text:
            coin_button.click()
            input('Please login before proceed! Press <enter> to continue!')
        if self.waitLogin():
            self.logger.debug("Login successful!")
            self.saveCookie()
        else:
            self.logger.info("Login failed!")
            return False
        return True

    @contextmanager
    def context(self):
        try:
            self.loggedin = self.login()
            yield self
        except Exception as e:
            self.logger.error(repr(e))
        finally:
            self.driver.close()

    def claimCoin(self):
        coin_button = self.waitForClass("COIN_BUTTON")
        if coin_button:
            if '簽到' in coin_button.text:
                self.logger.info( "Claiming coin for today, " + coin_button.text )
                coin_button.click()
                coin_button = self.waitForClass("COIN_BUTTON")
        else:
            self.logger.info("Coin button not found!")
            return False
        coin_value = self.getByClass("COIN_VALUE")
        if coin_value:
            last_value = ''
            # wait while the coin value counting
            while coin_value.text != last_value:
                last_value = coin_value.text
                sleep(1)
            self.logger.info("目前有 " + coin_value.text + " 蝦幣, " + coin_button.text)
        else:
            self.logger.info("Coin value not found!")
            return False
        return True

# TODO: import click
def main():
    with ShopeeWeb().context() as shopee:
        if shopee.loggedin:
            shopee.claimCoin()

if __name__ == "__main__":
    main()

