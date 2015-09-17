# -*- coding: utf-8 -*-

from willie.module import commands, rate, interval, rule, event

from datetime import datetime, timedelta
from dateutil import parser
import caldav
import pytz
import re

class Event():
	def __init__(self, title, start, end):
		self.title = title
		self.start = start
		self.end = end

	def fromVEvent(event):
		title = event._get_instance().vevent.summary.value
		start = parser.parse(str(event._get_instance().vevent.dtstart.value))
		end = parser.parse(str(event._get_instance().vevent.dtend.value))

		return Event(title, start, end)

	def formattime(input):
		if input.tzinfo:
			input = input.astimezone(pytz.timezone('Europe/Berlin'))
			return input.strftime("%d.%m.%Y %H:%M")
		else:
			return input.strftime("%d.%m.%Y")

	def formattimedelta(input):
		if input.days:
			return '{:.0f} Tag{}'.format(input.days, 'e' if input.days > 1 else '')
		elif input.seconds / (60*60) >= 1:
			return '{:.0f} Stunde{}'.format(input.seconds / (60*60), 'n' if round(input.seconds / (60*60)) != 1 else '')
		else:
			return '{:.0f} Minute{}'.format(input.seconds / 60, 'n' if round(input.seconds / 60) != 1 else '')

	def __str__(self):
		return '{} {} (Dauer: {})'.format(Event.formattime(self.start), self.title, Event.formattimedelta(self.end - self.start))

	def __lt__(self, other):
		if self.start.tzinfo:
			s_start = self.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			s_start = pytz.timezone('Europe/Berlin').localize(self.start)

		if other.start.tzinfo:
			o_start = other.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			o_start = pytz.timezone('Europe/Berlin').localize(other.start)

		return s_start < o_start

	def __gt__(self, other):
		if self.start.tzinfo:
			s_start = self.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			s_start = pytz.timezone('Europe/Berlin').localize(self.start)

		if other.start.tzinfo:
			o_start = other.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			o_start = pytz.timezone('Europe/Berlin').localize(other.start)

		return s_start > o_start

@rate(600)
@commands('ne', 'nextevent')
def getNextEvent(bot, trigger):
	bot.say('Nächstes Event: {}'.format(fetchNextEvent(bot)))

@interval(60*5)
def changeTopic(bot, trigger=None):
	if bot.memory.contains('topic'):
		nextEvent = fetchNextEvent(bot)

		m = re.search(r'N(?:ä|ae)chste(?:r|s) (?:Termin|Treffen|Event): (\d{2}\.\d{2}.\d{2,4}(?: \d{2}:\d{2})? [^\|]*)(?:\|)?', bot.memory['topic'])

		if m.group(1).strip() != str(nextEvent):
			topic = re.sub(r'(N(?:ä|ae)chste(?:r|s) (?:Termin|Treffen|Event)): \d{2}\.\d{2}.\d{2,4}( \d{2}:\d{2})? [^\|]*(\|)?', r'\1: {} |'.format(nextEvent), bot.memory['topic'])
		
			bot.write(('TOPIC', '{} :{}'.format(bot.config.freifunk.channel, topic)))

@event('TOPIC')
@rule('.*')
def topicChanged(bot, topic):
	bot.memory['topic'] = topic
	print('Topic changed! New Topic: {}'.format(topic))

def fetchNextEvent(bot):
	client = caldav.DAVClient(bot.config.freifunk.caldav_url)
	principal = client.principal()
	calendars = principal.calendars()

	eventlist = []
	if len(calendars) > 0:
		for calendar in calendars:
			if str(calendar) != bot.config.freifunk.caldav_cal:
				continue

			results = calendar.date_search(
				pytz.timezone('Europe/Berlin').localize(datetime.now()).astimezone(pytz.utc), (datetime.now() + timedelta(days=30*3)))

			for event in results:
				eventlist.append(Event.fromVEvent(event))

	if len(eventlist):
		eventlist = sorted(eventlist)

		return eventlist[0]