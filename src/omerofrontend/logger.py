import sys
import logging
from pathlib import Path 
from . import conf

class CustomFormatter(logging.Formatter):

    green ="\x1b[32m" 
    grey = "\x1b[38m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    magenta = "\x1b[35m"
    bold_red = "\x1b[31m"
    reset = "\x1b[0m"
    #format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    form = '%(process)d: %(asctime)s -%(levelname)s-: %(message)s'

    FORMATS = {
        logging.DEBUG: magenta + form + reset,
        logging.INFO: green + form + reset,
        logging.WARNING: yellow + form + reset,
        logging.ERROR: red + form + reset,
        logging.CRITICAL: bold_red + form + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt,datefmt='%Y%m%d %H:%M:%S')
        return formatter.format(record)

def setup_logger(level=logging.DEBUG):

    #check logfile existance
    if not Path(conf.LOG_FILE).is_file():
        Path(conf.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(conf.LOG_FILE).touch()
        
    logging.getLogger(conf.APP_NAME)
    fmtStr = '%(process)d: %(asctime)s -%(levelname)s-: %(message)s'
    
    logging.basicConfig(filename=conf.LOG_FILE, level=level,
                        format=fmtStr)
    localLogger = logging.StreamHandler(sys.stdout)
    llFmt = CustomFormatter()
    localLogger.setFormatter(llFmt)
    localLogger.setLevel(level)
    logging.getLogger(conf.APP_NAME).addHandler(localLogger)
        
    str_level = logging.getLevelName(level)
    info(f"Logger set up with level: {str_level}")


def log(level : str, msg : str):
    if level == "info":
        info(msg)
    elif level == "debug" or level == "dbg":
        debug(msg)
    elif level == "warning" or level == "warn":
        warning(msg)
    elif level == "error" or level == "err":
        error(msg)
    else:
        info(msg)            
            

def info(msg: str):
    logger().info(msg)
    
def warning(msg: str):
    logger().warning(msg)

def error(msg: str):
    logger().error(msg)

def debug(msg: str):
    logger().debug(msg)
    
def logger():
    return logging.getLogger(conf.APP_NAME)
