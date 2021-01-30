import os
import sys
import getopt
import pickle
import logging
import datetime
import inspect
from collections import abc
from contextlib import contextmanager
from time import gmtime, strftime, sleep, time

from selenium.common.exceptions import TimeoutException, NoSuchElementException, \
    StaleElementReferenceException, ElementClickInterceptedException
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webelement import WebElement

def help():
    print(
        '''Arguments:
        -h: Help
        -d: enable debug mode
        -f: disable file logging (enabled by default)
        -n: enable headless mode (disabled by default)
        -t: enable trace mode
        -D: dry run
        -s: run only the specified Shopee action
            'execClaimCoin'
            'execClaimCoupon'
            'execListSales'
        -m: run only the specified Momo action
            'execDailyTask'
        '''
    )
    sys.exit()

def initConfigClass(config):
    try:
        validArgs = [a for a in sys.argv[1:] if a != '-']
        opts, _ = getopt.getopt(validArgs, 'hdfntDs:m:')
    except:
        print('Warning: argument error!')
        sys.exit(1)
    for opt, arg in opts:
        if config.TRACE: print(f'opt {opt} {arg}')
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
        elif opt == '-s':
            config.Shopee = arg
        elif opt == '-m':
            config.Momo = arg

    config.init_logger()
    return config

@initConfigClass
class Config(object):

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

        "LOGIN_USER": "loginKey",
        "LOGIN_PASS": "password",

        "HOME_URL": "https://shopee.tw",
        "COIN_PAGE": "https://shopee.tw/shopee-coins"
    }
    path = os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def get(cls, name):
        return cls.configs.get(name)

    logger = None
    disableFileLogging = False

    Shopee = None
    Momo = None

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


def stripWrapper(codeFrame):
    while codeFrame.f_code.co_name == 'i_am_a_wrapper':
        codeFrame = codeFrame.f_back
    return codeFrame

def discardArgSelf(args, kwargs=None):
    _, *realargs = args # discard the first argument 'self'
    # realargs is a list not a tuple, TODO: beautify the case of single element
    if kwargs:
        for key, value in kwargs.items():
            realargs.append(f'{key}={value}')
    return tuple(realargs)

def printCaller(callerFrame, callingStr, printer):
    caller = callerFrame.f_code.co_name
    lineno = callerFrame.f_lineno
    printer(f'{caller}:{lineno}\t{callingStr}')

from functools import wraps

def traceMethod(printer=print):
    def decorator(function):
        if not Config.TRACE: return function
        @wraps(function)
        def i_am_a_wrapper(*args, **kwargs):
            result = function(*args, **kwargs)
            caller = stripWrapper(inspect.currentframe().f_back)
            realargs = discardArgSelf(args, kwargs)
            printCaller(caller, f'{function.__qualname__}{realargs} returned {result}', printer)
            return result
        return i_am_a_wrapper
    return decorator

def dryrunMethod(result=None):
    def decorator(function):
        if not Config.DRYRUN: return function
        @wraps(function)
        def i_am_a_wrapper(*args, **kwargs):
            caller = stripWrapper(inspect.currentframe().f_back)
            realargs = discardArgSelf(args, kwargs)
            printCaller(caller, f'{function.__qualname__}{realargs} run dry, pretended {result}', print)
            return result
        return i_am_a_wrapper
    return decorator

def guardFindElement(function):
    ''' don't raise exception if element/elements not found '''
    @wraps(function)
    def i_am_a_wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except NoSuchElementException:
            caller = stripWrapper(inspect.currentframe().f_back)
            realargs = discardArgSelf(args, kwargs)
            printCaller(caller, f'{function.__qualname__}{realargs} not found', print)
            return False
    return i_am_a_wrapper

class trapMethod:
    # class as a decorator
    ''' add an argument "trapFunction" to the decorated method '''
    # TODO: deal with pylint warning - Unexpected keyword argument 'trapFunction' in method call
    #   done by appending argument **kwargs to the decorated method

    def __call__(self, function):
        @wraps(function)
        def i_am_a_wrapper(*args, trapFunction=None, **kwargs):
            if not trapFunction and isinstance(args, abc.Collection) \
               and hasattr(args[0], 'trapFunction') and callable(args[0].trapFunction):
                # use default trap function
                trapFunction = args[0].trapFunction

            if trapFunction:
                try:
                    return function(*args, **kwargs)
                except Exception as e:
                    return trapFunction(*args, function_=function, exception_=e, **kwargs)
            else:
                return function(*args, **kwargs)

        return i_am_a_wrapper


class CastClass:

    @classmethod
    def quickCast(cls, base):
        ''' only if no new variable is added in the derived class '''
        base.__class__ = cls
        return base

    # TODO: Is it necessary? DerivedClass.__init__(self, base) is enough?
    @classmethod
    def castFrom(cls, base):
        derived = cls(base)

# TODO: need to update the __dict__ ?
#        vars(derived).update(vars(base))
# or
#        for key, value in base.__dict__.items():
#            derived.__dict__[key] = value

        return derived


class GuardedWebElement(WebElement, CastClass):
    ''' guard all find methods with @trapMethod() or @guardFindElement '''

    def __init__(self, webElm):
        WebElement.__init__(self, webElm._parent, webElm._id, webElm._w3c)

    @traceMethod()
    @trapMethod()
    def getByClass(self, selector, **kwargs):
        return GuardedWebElement(self.find_element_by_css_selector(selector))

    @traceMethod()
    @trapMethod()
    def getAllByClass(self, selector, **kwargs):
        return [GuardedWebElement(e) for e in self.find_elements_by_css_selector(selector)]

    @traceMethod()
    @trapMethod()
    def getById(self, id_, **kwargs):
        return GuardedWebElement(self.find_element_by_id(id_))


class Driver(webdriver.Chrome):

    try:
        TIMEOUT = Config.WAIT_TIMEOUT
    except:
        TIMEOUT = 5

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
        webdriver.Chrome.__init__(self, 'chromedriver',options=chrome_options)
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

    def getURL(self, url):
        return self.get(url)

    @trapMethod()
    def getByXPath(self, xpath, **kwargs):
        return GuardedWebElement(self.find_element_by_xpath(xpath))

    @trapMethod()
    def getByClass(self, selector, **kwargs):
        return GuardedWebElement(self.find_element_by_css_selector(selector))

    @trapMethod()
    def getAllByClass(self, selector, **kwargs):
        elements = self.find_elements_by_css_selector(selector)
        return [GuardedWebElement(e) for e in elements]

    def waitElementPresence(self, locator, timeout=TIMEOUT, timeoutMessage=''):
        element = WebDriverWait(self, timeout).until(
            EC.presence_of_element_located(locator), timeoutMessage
        )
        return GuardedWebElement(element) if isinstance(element, WebElement) else element

    @trapMethod()
    def waitForClass(self, selector, timeout=TIMEOUT, timeoutMessage='', **kwargs):
        return self.waitElementPresence((By.CSS_SELECTOR, selector), timeout, timeoutMessage)

    @trapMethod()
    def waitForXPath(self, xpath, timeout=TIMEOUT, timeoutMessage='', **kwargs):
        return self.waitElementPresence((By.XPATH, xpath), timeout, timeoutMessage)

    def waitElementsPresence(self, locator, timeout=TIMEOUT, timeoutMessage=''):
        elements = WebDriverWait(self, timeout).until(
            EC.presence_of_all_elements_located(locator), timeoutMessage
        )
        print(f'waitElementsPresence found {len(elements)} elements')
        return [GuardedWebElement(e) for e in elements]

    @trapMethod()
    def waitAllForClass(self, selector, timeout=TIMEOUT, timeoutMessage='', **kwargs):
        return self.waitElementsPresence((By.CSS_SELECTOR, selector), timeout, timeoutMessage)

    def waitElementsVisible(self, locator, timeout=TIMEOUT, timeoutMessage=''):
        elements = WebDriverWait(self, timeout).until(
            EC.visibility_of_any_elements_located(locator), timeoutMessage
        )
        print(f'waitElementsVisible found {len(elements)} elements')
        return [GuardedWebElement(e) for e in elements]

    @trapMethod()
    def waitVisibleForClass(self, selector, timeout=TIMEOUT, timeoutMessage='', **kwargs):
        return self.waitElementsVisible((By.CSS_SELECTOR, selector), timeout, timeoutMessage)


class BoundElement(WebElement):
    '''
    Bound with driver, method and target before wait/find, and with WebElement afterward.
    An element can be re-used with reinit() and change only different arguments.
    '''

    try:
        TIMEOUT = Config.WAIT_TIMEOUT
    except:
        TIMEOUT = 5

    @traceMethod()
    def __init__(self, driver, method, target, condition=EC.presence_of_element_located,
                 timeout=TIMEOUT, message='', trapFunction=None):
        self.reset(driver, method, target)
        self.reset_condition(condition, timeout, message, trapFunction)

    def reset(self, driver, method, target):
        super().__init__(driver, None)
        self.bound = False

        self.driver = driver
        self.method = method
        self.target = target

    def reset_condition(self, condition=EC.presence_of_element_located,
                        timeout=TIMEOUT, message='', trapFunction=None):
        super().__init__(self.driver, None)
        self.bound = False

        self.condition = condition
        self.timeout = timeout
        self.message = message

        self.trapFunction = trapFunction

    def reinit(self, target, method=None, driver=None,
               condition=None, timeout=None, message=None, trapFunction=None):
        ''' parameters are in reversed order of the __init__ method because of likelihood of reinitialization '''
        self.target = target
        if method: self.method = method
        if driver: self.driver = driver
        if condition: self.condition = condition
        if timeout: self.timeout = timeout
        if message: self.message = message
        if trapFunction: self.trapFunction = trapFunction
        self.bound = False
        return self

    def spawn(self, target, method=None, driver=None,
              condition=None, timeout=None, message=None, trapFunction=None):
        ''' spawn a new one with different attributes '''
        return self.spawn_from(self).reinit(target, method, driver, condition, timeout, message, trapFunction)

    @classmethod
    def spawn_from(cls, base, element=None):
        newElement = cls(base.driver, base.method, base.target, base.condition, base.timeout, base.message, base.trapFunction)
        if element:
            type(element).__init__(newElement, element._parent, element._id, element._w3c)
            newElement.bound = True
        return newElement

    def bind_result(self, result):
        if isinstance(result, abc.Collection):
            return [self.spawn_from(self, e) for e in result]
        elif isinstance(result, WebElement):
            return self.spawn_from(self, result)
        else:
            return result

    @traceMethod()
    @trapMethod()
    def wait(self, condition=None, timeout=None, message=None, **kwargs):
        _condition = condition if condition else self.condition
        _timeout = timeout if timeout else self.timeout
        _message = message if message else self.message

        result = WebDriverWait(self.driver, _timeout).until(
                    _condition((self.method, self.target)), _message
                )
        return self.bind_result(result)

    @traceMethod()
    @trapMethod()
    def find(self, target=None, method=None, **kwargs):
        ''' target is first because of likelihood of change '''
        if not target: target = self.target
        if not method: method = self.method
        if self.bound:
            result = self.find_element(method, target)
        else:
            result = self.driver.find_element(method, target)

        return self.bind_result(result)

    @traceMethod()
    @trapMethod()
    def find_all(self, target=None, method=None, **kwargs):
        ''' target is first because of likelihood of change '''
        if not target: target = self.target
        if not method: method = self.method
        if self.bound:
            result = self.find_elements(method, target)
        else:
            result = self.driver.find_elements(method, target)

        return self.bind_result(result)


class Crawler(object):

    class wrapConfig:
        # class as a decorator
        ''' add an argument "isConfig" to the decorated method '''
        def __call__(self, function):
            @wraps(function)
            def i_am_a_wrapper(self, name, isConfig=True, **kwargs):
                name = self.config.get(name) if isConfig else name
                return function(self, name, **kwargs)

            return i_am_a_wrapper

    config = Config
    logger = Config.logger

    from env import shopee_username as text_username
    from env import shopee_password as text_password
    from env import shopee_cookie as cookie

    def __init__(self):
        headless = (not self.config.DEBUG) or (self.config.path == '/code')
        self.driver = Driver(1200, 800, headless)

    @dryrunMethod({'success': 0, 'value': None, 'sessionId': None})
    @traceMethod() # or traceMethod(logger.info)
    @wrapConfig()
    def getURL(self, name):
        url = name
        return self.driver.get(url)

    @traceMethod()
    @wrapConfig()
    def waitForClass(self, name):
        selector = name
        return self.driver.waitElementPresence((By.CSS_SELECTOR, selector), self.config.WAIT_TIMEOUT)

    @traceMethod()
    @guardFindElement
    @wrapConfig()
    def getByClass(self, name):
        selector = name
        return self.driver.find_element_by_css_selector(selector)

    @guardFindElement
    @wrapConfig()
    def getByName(self, name):
        return self.driver.find_element_by_name(name)

    @guardFindElement
    @wrapConfig()
    def getAllByClass(self, name):
        selector = name
        return self.driver.find_elements_by_css_selector(selector)

    @guardFindElement
    @wrapConfig()
    def getAllByName(self, name):
        return self.driver.find_elements_by_name(name)

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
            self.driver.loadCookie(self.cookie)
            self.driver.refresh()
            self.logger.debug(f'Use {self.cookie} to login!')
        except:
            self.logger.info(f'{self.cookie} not found!')

    def preloadCookie(self):
        try:
            self.driver.preloadCookie(self.cookie)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to load cookie from "{self.cookie}"!')

    def loadCookie(self):
        try:
            self.driver.loadCookie(self.cookie)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to load cookie from "{self.cookie}"!')

    def saveCookie(self):
        try:
            self.driver.saveCookie(self.cookie)
        except Exception as e:
            self.logger.info(repr(e))
            self.logger.info(f'Failed to save cookie to "{self.cookie}"!')

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

            accountText.send_keys(self.text_username)
            passwordText.send_keys(self.text_password)
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


def catText(elements, delimit=False):
    text = ''
    for element in elements:
        text += element.text.replace('\n', '')
        if delimit and (text[-1] not in "，！。"): # these are UTF8's not ASCII's.
            text += '，'
    if text[-1] == '，': text = text[:-1]
    return text

class ShopeeWeb(Crawler):

    try:
        TIMEOUT = Crawler.config.WAIT_TIMEOUT
    except:
        TIMEOUT = 5

    URL_COINS   = 'https://shopee.tw/shopee-coins'
    SEL_AVATAR  = 'div.shopee-avatar'
    XPATH_COIN_DIV = '//div[text()="蝦幣獎勵"]/..'
    XPATH_COIN_VALUE  = XPATH_COIN_DIV + '/a/p'
    XPATH_COIN_BUTTON = XPATH_COIN_DIV + '/button'

    URL_COUPONS = 'https://shopee.tw/m/seller-voucher?smtt=0.0.7'
    SEL_COUPON = 'div._3ubyiy'

    URL_HOME = 'https://shopee.tw/'

    def __init__(self):
        self.driver = Driver(1200, 800, self.config.HEADLESS)
        self.cookie = 'cookie-shopee.pkl'

    @classmethod
    def _trapTimeout(cls, *args, **kwargs):
        #function  = kwargs.pop('function_')
        exception = kwargs.pop('exception_')
        #caller = stripWrapper(inspect.currentframe().f_back)
        #realargs = discardArgSelf(args, kwargs)
        if isinstance(exception, TimeoutException):
            return False
        raise exception

    @classmethod
    def _trapNoSuchElement(cls, *args, **kwargs):
        exception = kwargs.pop('exception_')
        if isinstance(exception, NoSuchElementException) or \
           isinstance(exception, StaleElementReferenceException):
            return False
        raise exception

    @classmethod
    def _trapWaitGet(cls, *args, **kwargs):
        exception = kwargs.pop('exception_')
        if isinstance(exception, TimeoutException) or \
           isinstance(exception, NoSuchElementException):
            return False
        raise exception

    @traceMethod() # Crawler.logger.info
    def waitLogin(self, timeout=TIMEOUT):
        return bool(BoundElement(self.driver, By.CSS_SELECTOR, self.SEL_AVATAR).wait(trapFunction=self._trapTimeout))

    def login(self, url, timeout=TIMEOUT):
        ''' login by cookie or manually '''
        self.preloadCookie()
        self.driver.getURL(url)
        if self.waitLogin(timeout):
            self.logger.debug("Login successful!")
            self.saveCookie()
        else:
            input('Please login before proceed! Press <enter> to continue!')
            if self.waitLogin(timeout):
                self.logger.debug("Login successful!")
                self.saveCookie()
            else:
                self.logger.info("Login failed!")
                return False
        return True

    @contextmanager
    def context(self, url, timeout=TIMEOUT):
        try:
            self.loggedin = self.login(url, timeout)
            yield self
        finally:
            self.driver.quit()

    def claimCoin(self):
        coin_button = BoundElement(self.driver, By.XPATH, self.XPATH_COIN_BUTTON).wait(trapFunction=self._trapTimeout)
        if coin_button:
            if '登入' in coin_button.text:
                coin_button.click()
                input('Please login before proceed! Press <enter> to continue!')
                coin_button = coin_button.wait(trapFunction=self._trapTimeout)
            if '簽到' in coin_button.text:
                self.logger.info("Claiming coin for today, " + coin_button.text)
                coin_button.click()
                coin_button = coin_button.wait(trapFunction=self._trapTimeout)
        else:
            self.logger.info("Coin button not found!")
            return False
        coin_value = coin_button.spawn(self.XPATH_COIN_VALUE).find(trapFunction=self._trapNoSuchElement)
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

    def click(self, clickSelector):
        element = self.driver.waitForClass(clickSelector, trapFunction=self._trapTimeout)
        if element:
            try:
                element.click()
                print('element clicked!')
            except ElementClickInterceptedException:
                # doesn't work here
                # self.driver.execute_script("arguments[0].click();", element)

                webdriver.ActionChains(self.driver).move_to_element(element).click(element).perform()
                print('element clicked by ActionChains!')
            except Exception as e:
                print(f'element not clickable!\n{type(e)}\n{e}')

    scrollPause = 0.5 # seconds
    scrollTimes = 2
    scrollPeriod = 5 # seconds
    repeatTimes = int(scrollPeriod / (scrollPause * scrollTimes))
    maxCoupons = 5

    def scrollDown(self):
        html = self.driver.find_element_by_tag_name('html')
        # don't do html.click() as the focus may be on a reference, thus html.click() will change to a different page
        # call the click(css selector) method above to click an element instead

        for _ in range(self.scrollTimes):
            html.send_keys(Keys.PAGE_DOWN)
            sleep(self.scrollPause)

        '''
        document.body.scrollHeight doesn't change!
        while height != last_height:
            last_height = height
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            html.send_keys(Keys.PAGE_DOWN)
            sleep(pause)
            height = self.driver.execute_script("return document.body.scrollHeight")
            print(f'height={height}')
        '''

    def claimCoupon(self):
        coupons = self.driver.waitAllForClass(self.SEL_COUPON, 5, trapFunction=self._trapTimeout)
        if not coupons: return 0

        def claim(self, coupon):
            name = ''
            terms = ''
            details = coupon.getByClass('div._2sbcJ3', trapFunction=self._trapNoSuchElement)
            if details:
                name = details.getByClass('h1', trapFunction=self._trapNoSuchElement)
                if name:
                    name = name.text
                else:
                    print('No name, Keep going!')
                    return False
                terms = details.getAllByClass('p')
                # some coupons have no term, not an error
                terms = catText(terms) if terms else ''
            else:
                print('No term, Keep going!')
                return False
            button = coupon.getByClass('button', trapFunction=self._trapNoSuchElement)
            if button:
                print(f'{name} {terms} button {button.text}')
                if '去逛逛' not in button.text:
                    try:
                        button.click()
                    except ElementClickInterceptedException:
                        # seems ok here
                        # self.driver.execute_script("arguments[0].click();", button)

                        webdriver.ActionChains(self.driver).move_to_element(button).click(button).perform()
                        print('Button clicked by ActionChains!')
                    except Exception as e:
                        print(f'Click error, Keep going!\n{type(e)}\n{e}')
                    else:
                        print('Button clicked!')
            else:
                text = coupon.getByClass('svg > g > text', trapFunction=self._trapNoSuchElement)
                if text:
                    print(f'{name} {terms} {text.text}')
                else:
                    print('Unknown element, Keep going!')
                    return False
            return True

        good = 0
        for coupon in coupons:
            try:
                # try to catch any WebElement exception, even access of "element.text" may throw an exception
                # as the page and elements are really dynamic
                claim(self, coupon)
            except:
                print('Exception, Keep going!')
            else:
                good += 1

        return good

    def printSalesItems(self, items):
        print(f'got {len(items)} items')
        for i in items:
            name = i.getByClass('div.flash-sale-item-card__item-name').text
            price = i.getByClass('div.flash-sale-item-card__current-price').text
            soldout = i.getByClass('div.flash-sale-sold-out', trapFunction=self._trapNoSuchElement)
            soldout = soldout.text if soldout else ''
            print(f'{name}\t{price}\t{soldout}')
        print(f'got {len(items)} items')

    def listSales(self, url=URL_HOME):
        self.driver.getURL(url)
        button = BoundElement(self.driver, By.CSS_SELECTOR, 'div.shopee-popup__close-btn', trapFunction=self._trapWaitGet).wait(timeout=2)
        if button:
            sleep(1)
            button.click() # close popup
        button = button.reinit('div.shopee-flash-sale-overview-carousel button').wait(timeout=1)
        if button: button.click()

        # wait for the first item
        self.driver.waitForClass('div.flash-sale-item-card')

        html = self.driver.find_element_by_tag_name('html')
        # don't do html.click()

        def scrollDown(self, last_height=-1, items=[]):
            if items:
                print(f'last {items[-1].getByClass("div.flash-sale-item-card__item-name").text}')
                self.driver.execute_script("arguments[0].scrollIntoView();", items[-1])
            else:
                html.send_keys(Keys.PAGE_DOWN)

            sleep(3)

            items  = self.driver.getAllByClass('div.flash-sale-item-card')
            height = self.driver.execute_script("return document.body.scrollHeight")

            if last_height > 0:
                print(f'items:{len(items)}, height: {last_height} => {height}')
            else:
                print(f'items:{len(items)}, height: {height}')
            return height, items

        last_height = -1
        height, items = scrollDown(self)

        while height != last_height:
            last_height = height
            height, items = scrollDown(self, last_height, items)

        self.printSalesItems(items)
        input('Press <enter> to continue!')

    def execClaimCoin(self):
        with self.context(self.URL_COINS):
            if self.loggedin:
                self.claimCoin()
                input('Press <enter> to close!')

    def execClaimCoupon(self, url=None):
        if not url: url = self.URL_COUPONS
        with self.context(url, 15):
            if self.loggedin:
                # click an element within the page, otherwise html.send_keys(Keys.PAGE_DOWN) has no effect
                self.click('img.uSG0wm.V1Fpl5')
                input('Press <enter> to continue')
                while True:
                    last_found = -1
                    found = 0
                    repeat = 0
                    while (self.maxCoupons <= 0 or found < self.maxCoupons) and \
                          (found != last_found or repeat < self.repeatTimes):
                        print('\n')
                        self.scrollDown()
                        found = self.claimCoupon()
                        if found == last_found:
                            repeat += 1
                        else:
                            last_found = found
                            repeat = 0
                    cmd = input('Press <enter> to continue, enter "r" to refesh!')
                    if cmd == 'r':
                        self.driver.getURL(url)
                        self.waitLogin(15)
                        self.click('img.uSG0wm.V1Fpl5')
                    elif cmd:
                        break

    def execListSales(self, url=URL_HOME):
        try:
            self.listSales(url)
        finally:
            self.driver.quit()

    def run(self):
        self.execClaimCoin()


class MomoWeb(Crawler):

    from env import momo_username, momo_password

    URL_HOME = 'https://www.momoshop.com.tw/'
    SEL_DAILYTASK1 = 'a#bt_0_244_01_P1_4_e1'
    SEL_DAILYTASK2 = 'a.days_btn.promo0_0Click'
    SEL_DAILYTASKAREA1 = 'div#html1.dailytaskArea'
    SEL_DAILYTASKAREA2 = 'div#html2.dailytaskArea'

    def __init__(self):
        self.driver = Driver(1200, 800, self.config.HEADLESS)
        self.cookie = 'cookie-momo.pkl'

    @classmethod
    def _raise(cls, *args, **kwargs):
        function  = kwargs.pop('function_')
        exception = kwargs.pop('exception_')
        caller = stripWrapper(inspect.currentframe().f_back)
        realargs = discardArgSelf(args, kwargs)
        printCaller(caller, f'{function.__qualname__}{realargs} failed, exit!', print)
        raise exception

    @classmethod
    def _trapTimeout(cls, *args, **kwargs):
        #function  = kwargs.pop('function_')
        exception = kwargs.pop('exception_')
        #caller = stripWrapper(inspect.currentframe().f_back)
        #realargs = discardArgSelf(args, kwargs)
        if isinstance(exception, TimeoutException):
            return False
        raise exception

    def dailyTask(self):
        ''' returned element/elements is/are not verified as any exception exits the execution. '''

        self.driver.getURL(self.URL_HOME)
        task_ref = BoundElement(self.driver, By.CSS_SELECTOR, self.SEL_DAILYTASK1, trapFunction=self._raise).wait()

        sleep(1)
        task_ref.click()
        task_ref = task_ref.reinit(self.SEL_DAILYTASK2).wait()

        sleep(1)
        task_ref.click()
        task_area = task_ref.reinit(self.SEL_DAILYTASKAREA1).wait()

        sec = task_area.find('sec', By.ID)
        last_value = ''
        # wait while the second ticking
        while sec.text != last_value:
            last_value = sec.text
            sleep(1)

        loginDiv = task_ref.reinit('div#ajaxLogin').wait()
        username    = loginDiv.find('input#memId')
        passwdShow  = loginDiv.find('input#passwd_show')
        password    = loginDiv.find('input#passwd')
        loginButton = loginDiv.find('dd.loginBtn > input')

        sleep(1)
        username.click()
        username.clear()
        username.send_keys(self.momo_username)
        sleep(1)
        passwdShow.click()
        sleep(1) # wait the input 'passwd' to be visible
        password.click()
        password.clear()
        password.send_keys(self.momo_password)
        sleep(1)
        loginButton.click()

        task_area = task_ref.reinit(self.SEL_DAILYTASKAREA2).wait()
        task_ref.reinit(self.SEL_DAILYTASKAREA2 + ' > div.dayon').wait(trapFunction=self._trapTimeout)
        titles = task_area.find_all('p.title')
        self.logger.info(catText(titles, True))

        # TODO: check the prize
        input('Press <enter> to close!')

    def execDailyTask(self):
        try:
            self.dailyTask()
        finally:
            self.driver.quit()

    def run(self):
        self.execDailyTask()

# TODO: import click
def main():
    if Config.Shopee:
        eval(f'ShopeeWeb().{Config.Shopee}()')
    elif Config.Momo:
        eval(f'MomoWeb().{Config.Momo}()')
    else:
        ShopeeWeb().run()
        MomoWeb().run()

if __name__ == "__main__":
    main()
