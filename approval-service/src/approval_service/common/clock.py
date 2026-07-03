import datetime


class Clock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)
