import config
import logging #info, warning, error and critical
import sys

def setup_logger(level=logging.DEBUG):

    logging.getLogger(config.APP_NAME)
    fmtStr = '%(process)d: %(asctime)s -%(levelname)s-: %(message)s'
    
    if level == logging.DEBUG:
        logging.basicConfig(filename='omero_app.log', level=level,
                           format=fmtStr)
        localLogger = logging.StreamHandler(sys.stdout)
        llFmt = logging.Formatter(fmtStr,datefmt='%Y%m%d %H:%M:%S')
        localLogger.setFormatter(llFmt)
        localLogger.setLevel(level)
        logging.getLogger(config.APP_NAME).addHandler(localLogger)
        
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
    return logging.getLogger(config.APP_NAME)
