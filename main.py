import json
import asyncio
import websockets
import re
import mailparser
from aiosmtpd.controller import Controller
from flask import Flask, jsonify
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship, sessionmaker, declarative_base

Base = declarative_base()

class Subject(Base):
    __tablename__ = 'subjects'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text())
    
class Mailbox(Base):
    __tablename__ = 'mailboxes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50))
    
    emails = relationship("Email", back_populates="mailbox")

    def serialize(self):
        return [{"subject": email.subject.content, "content": json.loads(email.content)} for email in self.emails]

class Email(Base):
    __tablename__ = 'emails'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    mailbox_id = Column(Integer, ForeignKey('mailboxes.id'))
    subject_id = Column(Integer, ForeignKey('subjects.id'))
    content = Column(Text()) # link or 6 digit otp
    
    mailbox = relationship("Mailbox", back_populates="emails")
    subject = relationship("Subject")

class Database:
    def __init__(self):
        self.engine = create_engine("sqlite:///nigga.sqlite", pool_size=20, max_overflow=30)
        Base.metadata.create_all(self.engine)

        self.get_session = sessionmaker(bind=self.engine)
        
    def upload_mail(self, mailbox_name, subject_name, messages):
        session = self.get_session()

        subject = session.query(Subject).filter(Subject.content == subject_name).first()
        if not subject:
            subject = Subject(content=subject_name)

        mailbox = session.query(Mailbox).filter(Mailbox.name == mailbox_name).first()
        if not mailbox:
            mailbox = Mailbox(name=mailbox_name)

        session.add(Email(content=json.dumps(messages), mailbox=mailbox, subject=subject)) 
        session.commit()

    def query_mails(self, mailbox_name):
        mailbox = self.get_session().query(Mailbox).filter(Mailbox.name == mailbox_name).first()
        if not mailbox:
            return []

        return mailbox.serialize()

class Websocket:
    def __init__(self, password, host, port):
        self.connected = set()
        self.password = password
        self.host = host
        self.port = port
    
    def get_host(self):
        return f"{self.host}:{self.port}"

    async def auth_handler(self, websocket):
        pwd = await websocket.recv()
        if pwd != self.password:
            return

        self.connected.add(websocket)
        try:
            await websocket.wait_closed()
        except:
            self.connected.remove(websocket)

    async def serve(self):
        async with websockets.serve(self.auth_handler, self.host, self.port):
            await asyncio.Future()
    
    def broadcast(self, message):
        websockets.broadcast(self.connected, json.dumps(message))

websocket_server = Websocket(
    "kek",
    "0.0.0.0",
    8123
)

database = Database()

app = Flask(__name__)
@app.route('/email/<email>')
def gettable(email):
    return jsonify(database.query_mails(email)), 200

class MailHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return '250 OK'

    def extract_body(content):
        b = email.message_from_bytes(content)
        if b.is_multipart():
            for part in b.walk():
                ctype = part.get_content_type()
                cdispo = str(part.get('Content-Disposition'))

                # skip any text/plain (txt) attachments
                if ctype == 'text/plain' and 'attachment' not in cdispo:
                    body = part.get_payload(decode=True)  # decode
                    break
        # not multipart - i.e. plain text, no attachments, keeping fingers crossed
        else:
            body = b.get_payload(decode=True)

        return body

    def extract_important_things(message):
        patterns = [
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 
            r'\d{6}'
        ]

        extracted = []
        for pattern in patterns:
            extracted.extend(re.findall(pattern, message)) 

        return extracted

    async def handle_DATA(self, server, session, envelope):
        target = envelope.rcpt_tos[0]

        body = extract_body(envelope.content)

        m = mailparser.parse_from_bytes(envelope.content)
        subject = str(m.subject)
        database.upload_mail(target, subject, extract_important_things(body))

        websocket_server.broadcast({"target": envelope.rcpt_tos, "payload": body, "subject": subject})
        return '250 Message accepted for delivery'



if __name__ == '__main__':
  controller = Controller(MailHandler(), port=25, hostname="")
  controller.start()
  print("Mail handler: 0.0.0.0:25")
  print("Websocket server: " + websocket_server.get_host())
  asyncio.run(app.run(debug=False, host="0.0.0.0", port=8080))
  asyncio.run(websocket_server.serve())
  controller.stop()