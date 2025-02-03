import conf
import logging #info, warning, error and critical
import sys


class CustomFormatter(logging.Formatter):

    green ="\x1b[36m" 
    grey = "\x1b[38m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    bold_red = "\x1b[31m"
    reset = "\x1b[0m"
    #format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    format = '%(process)d: %(asctime)s -%(levelname)s-: %(message)s'

    FORMATS = {
        logging.DEBUG: green + format + reset,
        logging.INFO: green + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt,datefmt='%Y%m%d %H:%M:%S')
        return formatter.format(record)

def setup_logger(level=logging.DEBUG):

    logging.getLogger(conf.APP_NAME)
    fmtStr = '%(process)d: %(asctime)s -%(levelname)s-: %(message)s'
    
    if level == logging.DEBUG:
        logging.basicConfig(filename='omero_app.log', level=level,
                           format=fmtStr)
        localLogger = logging.StreamHandler(sys.stdout)
        #llFmt = logging.Formatter(fmtStr,datefmt='%Y%m%d %H:%M:%S')
        llFmt = CustomFormatter()
        localLogger.setFormatter(llFmt)
        localLogger.setLevel(level)
        logging.getLogger(conf.APP_NAME).addHandler(localLogger)
        
    else: #only log to stdout
        logging.basicConfig(stream=sys.stdout, level=level,
                           format=fmtStr)
        
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
