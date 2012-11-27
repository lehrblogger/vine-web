import datetime
from flask import Flask, flash, render_template, redirect, request, session, url_for
from flask.ext.oauth import OAuth, OAuthException
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.wtf import Form, TextField, PasswordField, Required, Email, EqualTo
from sqlalchemy import select, and_
import xmlrpclib
import constants
from celery import chain
from celery_tasks import fetch_follows, score_edges

app = Flask(__name__)
app.debug = constants.debug
app.secret_key = constants.flask_secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://%s:%s@%s/%s' % (constants.web_mysql_user,
                                                                 constants.web_mysql_password,
                                                                 constants.db_host,
                                                                 constants.db_name)
app.config['SQLALCHEMY_POOL_SIZE'] = 100
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 3600
db = SQLAlchemy(app)
metadata = db.MetaData(bind = db.engine)
demos = db.Table('demos', metadata, autoload=True)
users = db.Table('users', metadata, autoload=True)
invites = db.Table('invites', metadata, autoload=True)
user_tasks = db.Table('user_tasks', metadata, autoload=True)
oauth = OAuth()
twitter = oauth.remote_app('twitter',
    base_url='https://api.twitter.com/1/',
    request_token_url='https://api.twitter.com/oauth/request_token',
    access_token_url='https://api.twitter.com/oauth/access_token',
    authorize_url='https://api.twitter.com/oauth/authenticate',
    consumer_key=constants.twitter_consumer_key,
    consumer_secret=constants.twitter_consumer_secret
)
xmlrpc_server = xmlrpclib.ServerProxy('http://%s:%s' % (constants.xmlrpc_server, constants.xmlrpc_port))

class InviteCodeForm(Form):
    code = TextField('code', validators=[Required()])
class CreateAccountForm(Form):
    email = TextField('Email', [Required(), Email(message='Please enter a valid email address.')])
    password = PasswordField('New Password', [Required(), EqualTo('confirm', message='Passwords must match')])
    confirm  = PasswordField('Repeat Password')
class ChangeEmailForm(Form):
    email = TextField('Email', [Required(), Email(message='Please enter a valid email address.')])
class ChangePasswordForm(Form):
    password = PasswordField('New Password', [Required(), EqualTo('confirm', message='Passwords must match')])
    confirm  = PasswordField('Repeat Password')

@app.route("/")
def index():
    user = session.get('vine_user')
    unused_invites = None
    used_invites = None
    if user:
        user_id = db.session.execute(select([users.c.id], users.c.name == user)).fetchone()['id'] # TODO fix indexing
        s = select([invites.c.code, invites.c.recipient],
                   and_(invites.c.sender == user_id, invites.c.recipient == None))
        unused_invites = db.session.execute(s).fetchall()
        s = select([invites.c.code, users.c.name, invites.c.used],
                   and_(invites.c.sender == user_id, invites.c.recipient == users.c.id, ))
        used_invites = db.session.execute(s).fetchall()
    return render_template('home.html', domain=constants.domain, user=user, unused_invites=unused_invites, used_invites=used_invites)

@app.route('/login')
def login():
    return twitter.authorize()

@app.route('/invite')
@app.route('/invite/<code>')
def invite(code=None):
    user = session.get('vine_user')
    form = InviteCodeForm()
    if user:
        return redirect(url_for('index'))
    invite = db.session.execute(select([users.c.name, invites.c.recipient],
                                and_(users.c.id == invites.c.sender, invites.c.code == code))).fetchone()
    if invite:
        if invite['recipient']:
            flash('Sorry, that invite code has already been used.', 'error')
        else:
            session['invite_code'] = code
            return render_template('invite.html', sender=invite[0])
    else:
        flash('Sorry, that invite code isn\'t valid.', 'error')
    return render_template('invite.html', form=form)

@app.route('/check_invite', methods=['POST'])
def check_invite():
    form = InviteCodeForm(request.form)
    if form.validate():
        code = form.code.data
        return redirect(url_for('invite', code=code))
    flash('Please enter an invite code.', 'error')
    return redirect(request.referrer or url_for('index'))

@app.route('/logout')
def logout():
    session.pop('vine_user', None)
    flash('You were signed out', 'error')
    return redirect(request.referrer or url_for('index'))

@twitter.tokengetter
def get_twitter_token():
    s = select([users.c.twitter_token, users.c.twitter_secret], users.c.name == session.get('vine_user'))
    return db.session.execute(s).fetchone()

def clear_bad_oauth_cookies(fn):
    def wrapped():
        try:
            return fn()
        except OAuthException, e:
            if e.message == 'Invalid response from twitter':
                session.pop('vine_user', None)
                return fn()
            else:
                raise e
    return wrapped
@app.route('/twitter/oauth_callback')
@clear_bad_oauth_cookies
@twitter.authorized_handler
def oauth_authorized(resp):
    if resp is None:
        flash(u'You cancelled the Twitter authorization flow.', 'error')
        return redirect(url_for('index'))
    twitter_user = resp['screen_name'].lower()
    s = select([users.c.id, users.c.email, users.c.twitter_id, users.c.twitter_token, users.c.twitter_secret],
            and_(users.c.name == twitter_user))
    found_user = db.session.execute(s).fetchone()
    if found_user:
        if not found_user.twitter_id == resp['user_id'] or \
           not found_user.twitter_token == resp['oauth_token'] or \
           not found_user.twitter_secret == resp['oauth_token_secret']:
            db.session.execute(users.update().\
                               where(users.c.name == twitter_user).\
                               values(twitter_id=resp['user_id'],
                                      twitter_token=resp['oauth_token'],
                                      twitter_secret=resp['oauth_token_secret']))
        result = chain(fetch_follows.s(found_user.id, resp['user_id'], resp['oauth_token'], resp['oauth_token_secret']),
                       score_edges.s())()
        db.session.execute(user_tasks.insert().\
                           values(user_id=found_user.id,
                                  celery_task_id=result,
                                  celery_task_type='fetch_follows'))
        session['vine_user'] = twitter_user
        flash('You were signed in as %s' % twitter_user, 'error')
    else:
        db.session.execute(users.insert().\
                           values(name=twitter_user,
                                  twitter_token=resp['oauth_token'],
                                  twitter_secret=resp['oauth_token_secret']))
    db.session.commit()
    if found_user and found_user.email:  # if we have a user that's finished the process
        session['vine_user'] = twitter_user
        flash('You were signed in as %s' % twitter_user, 'error')
    elif found_user and not found_user.email:
        return redirect(url_for('create_account'))
        flash('You were signed in as %s, but still need to enter an email address and password' % twitter_user, 'error')
    else:
        if session.get('invite_code'):
            s = select([invites], and_(invites.c.code == session['invite_code'], invites.c.recipient == None))
            if db.session.execute(s).fetchone():
                session['twitter_user'] = twitter_user
                return redirect(url_for('create_account'))
            else:
                flash('Sorry, that invite code is not valid.', 'error')
        else:
            flash('Sorry, but you need an invite code to sign up.', 'error')
    return redirect(url_for('index'))

@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'GET':
        if session.get('vine_user'):
            return redirect(url_for('settings'))
        user = session.get('twitter_user')
        form = CreateAccountForm()
        return render_template('create_account.html', user=user, form=form)
    else:
        if session.get('invite_code'):
            s = select([invites], and_(invites.c.code == session['invite_code'], invites.c.recipient == None))
            if db.session.execute(s).fetchone():
                form = CreateAccountForm(request.form)
                if form.validate():
                    try:
                        _register(session.get('twitter_user'), form.password.data)
                        db.session.execute(users.update().\
                                       where(users.c.name == session.get('twitter_user')).\
                                       values(email=form.email.data))
                        user_id = db.session.execute(select([users.c.id], users.c.name == session.get('twitter_user'))).fetchone()[0]
                        db.session.execute(invites.update().\
                                         where(invites.c.code == session['invite_code']).\
                                         values(recipient=user_id, used=datetime.datetime.now()))
                        db.session.commit()
                        session['vine_user'] = session.get('twitter_user')
                        session.pop('twitter_user')
                        session.pop('invite_code')
                        flash('You signed up as %s' % session.get('vine_user'), 'error')
                    except xmlrpclib.ProtocolError, e:
                        flash('There was an error creating your XMPP account.', 'error')
                        return redirect(url_for('create_account'))
                else:
                    #flash('There was an error in the form.', 'error')
                    return redirect(url_for('create_account'))
            else:
                flash('Sorry, that invite code is not valid.', 'error')
        else:
            flash('Sorry, but you need an invite code to sign up.', 'error')
        return redirect(url_for('index'))

@app.route("/demo/")
def no_demo():
    return redirect(url_for('index'))

@app.route("/demo/<token>/")
def demo(token):
    s = select([users.c.name, demos.c.password],
               and_(users.c.id == demos.c.user_id, demos.c.token == token))
    found_demo = db.session.execute(s).fetchone()
    if found_demo:
        return render_template('demo.html', server=constants.domain, username=found_demo['name'], password=found_demo['password'])
    return redirect(url_for('index'))

@app.route("/setup")
def setup():
    user = session.get('vine_user')
    return render_template('setup.html', user=user)

@app.route("/settings")
def settings():
    user = session.get('vine_user')
    if not user:
        return redirect(url_for('index'))
    if request.method == 'GET':
        user_email = db.session.execute(select([users.c.email], users.c.name == user)).fetchone()
        form = ChangeEmailForm()
        form.email.data = user_email.email
    else:
        form = ChangeEmailForm(request.form)
        if form.validate():
            db.session.execute(users.update().where(users.c.name == user).values(email=form.email.data))
            db.session.commit()
            flash('Your email address has been changed.', 'error')
    return render_template('settings.html', user=user, form=form)

@app.route('/settings/change_password', methods=['GET', 'POST'])
def change_password():
    user = session.get('vine_user')
    if not user:
        return redirect(url_for('index'))
    if request.method == 'GET':
        form = ChangePasswordForm()
    else:
        form = ChangePasswordForm(request.form)
        if form.validate():
            try:
                _change_password(user, form.password.data)
                flash('Your password has been changed.', 'error')
            except xmlrpclib.ProtocolError, e:
                flash('There was an error changing your XMPP password.', 'error')
                return redirect(url_for('change_password'))
    return render_template('change_password.html', user=user, form=form)

@app.route("/about")
def about():
    user = session.get('vine_user')
    return render_template('about.html', user=user)

@app.route("/legal")
def legal():
    user = session.get('vine_user')
    return render_template('legal.html', user=user)

@app.route("/contacts")
def contacts():
    user = session.get('vine_user')
    return render_template('contacts.html', user=user)

@app.errorhandler(404)
def page_not_found(e=None):
    return render_template('404.html'), 404

@app.route("/50x.html")
@app.errorhandler(500)
def page_not_found(e=None):
    return render_template('500.html'), 500

def _register(user, password):
    _xmlrpc_command('register', {
        'user': user,
        'host': constants.domain,
        'password': password
    })
def _change_password(user, password):
    _xmlrpc_command('change_password', {
        'user': user,
        'host': constants.domain,
        'newpass': password
    })
def _xmlrpc_command(command, data):
    fn = getattr(xmlrpc_server, command)
    return fn({
        'user': constants.web_xmlrpc_user,
        'server': constants.domain,
        'password': constants.web_xmlrpc_password
    }, data)

if __name__ == "__main__":
    #NOTE this code only gets run when you're using Flask's built-in server, so gunicorn never sees this code.
    app.run(host='0.0.0.0', port=8000)
