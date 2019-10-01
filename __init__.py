# -*- coding: utf-8 -*-

import logging
import sys

def set_logger(logger_name):
    """Creates a logger with requested name."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging_level)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging_level)
    formatter = logging.Formatter('%(asctime)s; %(name)s; %(levelname)s; %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

def get_logger(logger_name):
    """Returns a logger instance by the name."""
    return set_logger(logger_name)

logging_level = logging.DEBUG
logger = get_logger(__name__)
