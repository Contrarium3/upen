import logging

def get_logger():
    log_file = f"log.txt"  
    logger = logging.getLogger(f"logger")
    logger.setLevel(logging.DEBUG)
    
    # Check if a handler already exists to avoid adding multiple handlers
    if not logger.hasHandlers():
        handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def log_error(message, act = None):
    logger = get_logger()
    if act:
        logger.error(f"❌ Error processing BOOK: {act} - {message}\n")
        print(f"❌ Error processing BOOK: {act} - {message}")
    else:
        logger.error(f'❌ {message}\n')
        print(f'❌ {message}')

def log_info(message):
    logger = get_logger()
    logger.info(message)


