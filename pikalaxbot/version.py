import datetime

__all__ = ('version',)

now = datetime.datetime.utcnow()
version = f'0.1.{now.year}{now.month:02d}{now.day:02d}'
