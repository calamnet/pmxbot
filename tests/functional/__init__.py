from __future__ import print_function

import subprocess
import os
import sys
import time
import sqlite3
import urlparse

import irc.client
import py.test

import pmxbot.dictlib

class TestingClient(object):
	"""
	A simple client simulating a user other than the pmxbot
	"""
	def __init__(self, server, port, nickname):
		self.irc = irc.client.IRC()
		self.c = self.irc.server()
		self.c.connect(server, port, nickname)
		self.irc.process_once(0.1)

	def send_message(self, channel, message):
		self.c.privmsg(channel, message)
		time.sleep(0.05)

class PmxbotHarness(object):
	config = pmxbot.dictlib.ConfigDict(
		server_port = 6668,
		bot_nickname = 'pmxbotTest',
		log_channels = ['#logged'],
		other_channels = ['#inane'],
		database = "sqlite:tests/functional/pmxbot.sqlite",
	)

	@classmethod
	def setup_class(cls):
		"""Start a tcl IRC server, launch the bot, and
		ask it to do stuff"""
		path = os.path.dirname(os.path.abspath(__file__))
		cls.config_fn = os.path.join(path, 'testconf.yaml')
		cls.config.to_yaml(cls.config_fn)
		cls.dbfile = urlparse.urlparse(cls.config['database']).path
		cls.db = sqlite3.connect(cls.dbfile)
		try:
			cls.server = subprocess.Popen(['tclsh', os.path.join(path,
				'tclircd/ircd.tcl')], stdout=open(os.path.devnull, 'w'),
				stderr=open(os.path.devnull, 'w'))
		except OSError:
			py.test.skip("Unable to launch irc server (tclsh must be in the "
				"path)")
		time.sleep(0.5)
		# add './plugins' to the path so we get some pmxbot commands specific
		#  for testing.
		env = os.environ.copy()
		env['PYTHONPATH'] = os.path.join(path, 'plugins')
		try:
			# Launch pmxbot using Python directly (rather than through
			#  the console entry point, which can't be properly
			#  .terminate()d on Windows.
			cls.bot = subprocess.Popen([sys.executable, '-c',
				'from pmxbot.core import run; run()', cls.config_fn],
				env=env)
		except OSError:
			py.test.skip("Unable to launch pmxbot (pmxbot must be installed)")
		time.sleep(5)
		cls.client = TestingClient('localhost', 6668, 'testingbot')

	def check_logs(cls, channel='', nick='', message=''):
		if channel.startswith('#'):
			channel = channel[1:]
		time.sleep(0.1)
		cursor = cls.db.cursor()
		query = "select * from logs where 1=1"
		if channel:
			query += " and channel = :channel"
		if nick:
			query += " and nick = :nick"
		if message:
			query += " and message = :message"
		cursor.execute(query, dict(
			channel = channel,
			nick = nick,
			message = message,
			))
		res = cursor.fetchall()
		print(res)
		return len(res) >= 1

	@classmethod
	def teardown_class(cls):
		os.remove(cls.config_fn)
		if hasattr(cls, 'bot') and not cls.bot.poll():
			cls.bot.terminate()
			cls.bot.wait()
		if hasattr(cls, 'server') and cls.server.poll() == None:
			cls.server.terminate()
			cls.server.wait()
		if hasattr(cls, 'db'):
			cls.db.rollback()
			cls.db.close()
			del cls.db
		if hasattr(cls, 'client'):
			del cls.client
		# wait up to 10 seconds for the file to be removable
		for x in range(100):
			try:
				if os.path.isfile(cls.dbfile): os.remove(cls.dbfile)
				break
			except OSError:
				time.sleep(.1)
		else:
			raise RuntimeError('Could not remove log db', cls.dbfile)
