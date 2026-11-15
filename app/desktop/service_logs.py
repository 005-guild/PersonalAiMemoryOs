"""Drain owned startup-helper output into a bounded rotating log."""
import logging
from logging.handlers import RotatingFileHandler
from threading import Thread


def capture_output(process,path,*,max_bytes=8*1024*1024,backups=3):
    handler=RotatingFileHandler(path,maxBytes=max_bytes,backupCount=backups,encoding='utf-8')
    stream=getattr(process,'stdout',None)
    if stream is None:
        handler.close()
        return None
    def drain():
        try:
            for chunk in iter(lambda:stream.read(4096),b''):
                message=chunk.decode('utf-8',errors='replace')
                handler.emit(logging.LogRecord('local-rag-output',logging.INFO,'',0,message,(),None))
        finally:
            stream.close();handler.close()
    thread=Thread(target=drain,name='local-rag-log-reader',daemon=True)
    thread.start()
    return thread
