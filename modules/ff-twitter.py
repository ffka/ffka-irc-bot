# -*- coding: utf-8 -*-

from willie.module import interval

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
import datetime
from twython import Twython, TwythonStreamer

Base = declarative_base()
session_maker_instance = None


# already defined in ff-nodeinfo, better move to separate class file
class Highscore(Base):
    __tablename__ = 'highscores'

    name = Column(String, primary_key=True)
    date = Column(DateTime)
    count = Column(Integer)

    def __init__(self, name):
        self.name = name
        self.count = 0

    def update(self, count):
        if self.count < count:
            self.count = count
            self.date = datetime.datetime.now()
            return True
        return False


def setup(bot):
    if 'ff' not in bot.memory:
        bot.memory['ff'] = {}

    bot.memory['ff']['last_highscore_dt'] = {}

    check_highscore(bot, initial=True)


@interval(30)
def check_highscore(bot, initial=False):
    engine = create_engine('sqlite:///{0}'.format(bot.config.freifunk.db_path))
    session_maker_instance = sessionmaker(engine)

    session = session_maker_instance()

    for highscore in session.query(Highscore):
        if highscore.name not in bot.memory['ff']['last_highscore_dt'] \
                or (bot.memory['ff']['last_highscore_dt'][highscore.name]
                and bot.memory['ff']['last_highscore_dt'][highscore.name] < highscore.date):
            bot.memory['ff']['last_highscore_dt'][highscore.name] = highscore.date

            if not initial:
                print('Neuer Highscore: {:d} {:s}'.format(highscore.count, highscore.name.capitalize()))

                twitter = Twython(
                    bot.config.freifunk.twitter_api_key,
                    bot.config.freifunk.twitter_api_secret,
                    bot.config.freifunk.twitter_oauth_key,
                    bot.config.freifunk.twitter_oauth_secret)
                twitter.update_status(
                    status='Neuer Highscore: {:d} {:s}'.format(highscore.count, highscore.name.capitalize()))

    session.close()
