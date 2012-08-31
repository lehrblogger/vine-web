#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import logging
from optparse import OptionParser
from collections import defaultdict
import constants
import MySQLdb
from MySQLdb import IntegrityError, OperationalError
import sleekxmpp

THRESHOLD = 0
PAGESIZE = 20

class EdgeCalculator(sleekxmpp.ClientXMPP):
    def __init__(self):
        sleekxmpp.ClientXMPP.__init__(self, '%s@%s' % (constants.graph_xmpp_user, constants.server), constants.graph_xmpp_password)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)
        self.db = None
        self.cursor = None
        self.senders = None
        self.db_connect()
        self.old_edge_offset = 0
        self.in_delete_phase = True

    def start(self, event):
        self.process_logs()
        #self.update_next_old_edge()
        self.cleanup()  # to disconnect when finished
    
    #TODO think through failure cases

    def process_logs(self):
        self.senders = defaultdict(lambda : defaultdict(int))
        def process_log_type(db_query_fn, multiplier_fn):
            offset = 0
            messages = True
            while messages:
                messages = db_query_fn(offset)
                offset += PAGESIZE
                for message in messages:
                    sender, recipient, body = message
                    logging.info((sender, recipient, body))
                    self.senders[sender][recipient] += multiplier_fn(body)
        process_log_type(self.db_fetch_messages, lambda s: len(s))
        process_log_type(self.db_fetch_topics,  lambda s: len(s))
        process_log_type(self.db_fetch_whispers, lambda s: 2 * len(s))
        process_log_type(self.db_fetch_invites,  lambda s: 100)
        process_log_type(self.db_fetch_kicks,  lambda s: -100)
        
        import json
        logging.info('\n' + json.dumps(self.senders, indent=4))
    
    def update_next_old_edge(self):
        old_edge = # fetch next edge with offset = self.old_edge_offset, limit = 1
        if old_edge:
            if self.senders.has_edge(old_edge.frm, old_edge.to):
                self.senders.delete_edge(old_edge.frm, old_edge.to)
                self.update_next_old_edge()
            else:
                self.send_message_to_leaf('/del_friendship %s %s' % (user1, user2))
        else:
            self.in_delete_phase = False
            self.update_next_new_edge()
    
    def update_next_new_edge(self):
        new_edge = []# pop one from  self.senders:
        if new_edge:
            self.send_message_to_leaf('/new_friendship %s %s' % (user1, user2))
    
    def message(self, msg):
        logging.info(msg)
        if True: #got success response and if from leaf use
            # use Your /new_friendship command was successful. and Your /del_friendship command was successful.
            # put usernames in response
            if self.in_delete_phase:
                # delete edge from database
                self.update_next_old_edge()
                
            else: # was /new_friendship command:
                # create edge in the database
                self.update_next_new_edge()
            
    def send_message_to_leaf(self, body):
        msg = self.Message()
        msg['to'] = 'leaf1.dev.vine.im'
        msg['body'] = body
        msg.send()
    
    def db_fetch_messages(self, offset):
        return self.db_execute_and_fetchall("""SELECT sender.name, recipient.name, messages.body
                                               FROM messages, message_recipients, users as sender, users as recipient
                                               WHERE messages.id = message_recipients.message_id
                                               AND messages.parent_command_id IS NULL
                                               AND messages.sender_id IS NOT NULL
                                               AND sender.id = messages.sender_id
                                               AND recipient.id = message_recipients.recipient_id
                                               AND messages.sent_on > %(startdate)s
                                               LIMIT %(pagesize)s
                                               OFFSET %(offset)s
                                            """, {
                                               'startdate': 0,
                                               'pagesize': PAGESIZE,
                                               'offset': offset
                                            })
    
    def db_fetch_topics(self, offset):
        return self.db_execute_and_fetchall("""SELECT sender.name, recipient.name, commands.string
                                               FROM commands, messages, message_recipients, users as sender, users as recipient
                                               WHERE commands.command_name = 'topic'
                                               AND commands.sender_id = sender.id
                                               AND commands.id = messages.parent_command_id
                                               AND messages.id = message_recipients.message_id
                                               AND recipient.id = message_recipients.recipient_id
                                               AND sender.id != message_recipients.recipient_id
                                               AND commands.string IS NOT NULL
                                               AND commands.sent_on > %(startdate)s
                                               LIMIT %(pagesize)s
                                               OFFSET %(offset)s
                                            """, {
                                               'startdate': 0,
                                               'pagesize': PAGESIZE,
                                               'offset': offset
                                            })
    
    def db_fetch_whispers(self, offset):
        return self.db_execute_and_fetchall("""SELECT sender.name, recipient.name, messages.body
                                               FROM commands, messages, message_recipients, users as sender, users as recipient
                                               WHERE commands.command_name = 'whisper'
                                               AND messages.id = message_recipients.message_id
                                               AND messages.sender_id IS NOT NULL
                                               AND sender.id = messages.sender_id
                                               AND recipient.id = message_recipients.recipient_id
                                               AND commands.id = messages.parent_command_id
                                               AND commands.sent_on > %(startdate)s
                                               LIMIT %(pagesize)s
                                               OFFSET %(offset)s
                                            """, {
                                               'startdate': 0,
                                               'pagesize': PAGESIZE,
                                               'offset': offset
                                            })
    
    def db_fetch_invites(self, offset):
        return self.db_execute_and_fetchall("""SELECT sender.name, commands.token, messages.body
                                               FROM commands, messages, message_recipients, users as sender
                                               WHERE commands.command_name = 'invite'
                                               AND commands.sender_id IS NOT NULL
                                               AND sender.id = commands.sender_id
                                               AND commands.is_valid IS TRUE
                                               AND messages.sender_id IS NULL
                                               AND messages.parent_message_id IS NULL
                                               AND messages.parent_command_id = commands.id
                                               AND messages.body NOT LIKE 'Sorry, %%'
                                               #TODO fix this ugly hack, which assumes that if a response to a command begins with 'Sorry', 
                                               # there was an ExecutionError, and all other responses indicate a successful command.
                                               AND messages.id = message_recipients.message_id
                                               AND message_recipients.recipient_id = sender.id
                                               AND commands.sent_on > %(startdate)s
                                               LIMIT %(pagesize)s
                                               OFFSET %(offset)s
                                            """, {
                                               'startdate': 0,
                                               'pagesize': PAGESIZE,
                                               'offset': offset
                                            })
    
    def db_fetch_kicks(self, offset):
        return self.db_execute_and_fetchall("""SELECT sender.name, commands.token, messages.body
                                               FROM commands, messages, message_recipients, users as sender
                                               WHERE commands.sender_id IS NOT NULL
                                               AND sender.id = commands.sender_id
                                               AND commands.sent_on > %(startdate)s
                                               AND commands.is_valid IS TRUE
                                               AND commands.command_name = 'kick'
                                               AND messages.sender_id IS NULL
                                               AND messages.parent_message_id IS NULL
                                               AND messages.parent_command_id = commands.id
                                               AND messages.body NOT LIKE 'Sorry, %%'
                                               AND messages.id = message_recipients.message_id
                                               AND message_recipients.recipient_id = sender.id
                                               LIMIT %(pagesize)s
                                               OFFSET %(offset)s
                                            """, {
                                               'startdate': 0,
                                               'pagesize': PAGESIZE,
                                               'offset': offset
                                            })    
    
    def db_execute_and_fetchall(self, query, data={}, strip_pairs=False):
        self.db_execute(query, data)
        fetched = self.cursor.fetchall()
        if fetched and len(fetched) > 0:
            if strip_pairs:
                return [result[0] for result in fetched]
            else:
                return fetched
        return []
    
    def db_execute(self, query, data={}):
        logging.info(query % data)
        if not self.db or not self.cursor:
            logging.info("Database connection missing, attempting to reconnect and retry query")
            if self.db:
                self.db.close()
            self.db_connect()
        try:
            self.cursor.execute(query, data)
        except MySQLdb.OperationalError, e:
            logging.info('Database OperationalError %s for query, will retry: %s' % (e, query % data))
            self.db_connect()  # Try again, but only once
            self.cursor.execute(query, data)
        return self.db.insert_id()
    
    def db_connect(self):
        try:
            self.db = MySQLdb.connect(constants.db_host,
                                      constants.graph_mysql_user,
                                      constants.graph_mysql_password,
                                      constants.db_name)
            self.db.autocommit(True)
            self.cursor = self.db.cursor()
            logging.info("Database connection created")
        except MySQLdb.Error, e:
            logging.error('Database connection and/or cursor creation failed with %d: %s' % (e.args[0], e.args[1]))
            self.cleanup()
    
    def cleanup(self):
        if self.db:
            self.db.close()
        sys.exit(1)
    

if __name__ == '__main__':
    optp = OptionParser()
    optp.add_option('-q', '--quiet', help='set logging to ERROR',
                    action='store_const', dest='loglevel',
                    const=logging.ERROR, default=logging.INFO)
    optp.add_option('-v', '--verbose', help='set logging to COMM',
                    action='store_const', dest='loglevel',
                    const=5, default=logging.INFO)
    opts, args = optp.parse_args()

    logging.basicConfig(level=opts.loglevel,
                        format='%(asctime)-15s graph %(levelname)-8s %(message)s')

    calculator = EdgeCalculator()
    calculator.register_plugin('xep_0030') # Service Discovery
    calculator.register_plugin('xep_0004') # Data Forms
    calculator.register_plugin('xep_0060') # PubSub
    calculator.register_plugin('xep_0199') # XMPP Ping

    if calculator.connect((constants.server_ip, constants.client_port)):# caused a weird _der_cert error
        calculator.process(block=True)
        logging.info("Done")
    else:
        logging.info("Unable to connect.")
