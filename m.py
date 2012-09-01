from flask import Flask, request, render_template, redirect, url_for, flash

from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import (LoginManager, current_user, login_required,
                            login_user, logout_user, UserMixin, AnonymousUser,
                            confirm_login, fresh_login_required)
from bcrypt import gensalt, hashpw

import sys
from collections import OrderedDict

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)

SECRET_KEY = "yeah, not actually a secret"
DEBUG = True


app.config.from_object(__name__)

login_manager = LoginManager()


class TreeNode(object):
    def __init__(self, value=None):
        self.value = value
        self.parent = None
        self.children = OrderedDict()
        #self.children = defaultdict(lambda: None) 

    def __iter__(self):
        return self.children.iteritems()

    def __getitem__(self, item):
        return self.children[item]

    def __getattr__(self, attr):
        try:
            return self.children[attr]
        except KeyError:
            raise AttributeError(attr)

    def add_child(self, node, delimeter='.'):
        #for item in node.value.split(delimeter):
        items = node.split(delimeter)

        if items:
            item = items[0]
            if item not in self.children:
                self.children[item] = TreeNode(item)
                self.children[item].parent = self

            if len(items) > 1:
                self.children[item].add_child(delimeter.join(items[1:]))

    #def _add_child_to_self(self, node):
    #    self.children[node.value] = node
    #    #self.child.append(node)
    #    node.parent = self

    def get_lineage(self):
        if self.parent is None:
            return [self]

        lineage = self.parent.get_lineage()
        lineage.append(self)

        return lineage

    def __repr__(self):
        return self.value

a = TreeNode()
#b = TreeNode('b')
#c = TreeNode('c')
#d = TreeNode('d')
#e = TreeNode('e')
#f = TreeNode('f')
#g = TreeNode('g')

a.add_child('b.c.d')
a.add_child('b.c.e')
a.add_child('b.c.f')

#print a.children['b'].children['c'].parent
#print a.children['b'].children['c'].get_lineage()

#a.add_child(c)

#c.add_child(d)
#d.add_child(e)

#print b.get_lineage()


#sys.exit(0)


@login_manager.user_loader
def load_user(id):
    return User.query.filter_by(id=id).first()

login_manager.setup_app(app)
login_manager.login_view = "loginpage"

class User(db.Model, UserMixin):
    #__tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True, nullable=False)
    salt = db.Column(db.String(32), unique=False, nullable=False)
    passwd = db.Column(db.String(60), unique=False, nullable=False)

    emails = db.relationship

    def __init__(self, email, password):
        self.email = email

        salt = gensalt(10)
        self.salt = salt
        self.passwd = hashpw(password, salt)

    def __repr__(self):
        return '<User %r>' % (self.email)


class ImapAccount(db.Model):
    #__tablename__ = 'imap_accounts'


    id = db.Column(db.Integer, primary_key=True)
    # TODO: add name field
    server = db.Column(db.String(128), unique=False)
    email = db.Column(db.String(128), nullable=False)
    passwd = db.Column(db.String(128), unique=False, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User',
        backref=db.backref('imapaccounts', lazy='dynamic'))

    def __init__(self, server, email, password, user):
        self.server = server
        self.email = email
        self.passwd = password
        self.user = user

    def __repr__(self):
        return '<Imap Account %r>' % (self.email)


@app.route('/', methods=['GET', 'POST'])
def loginpage():
    def check_credential(u):
        return u and hashpw(password, u.salt) == u.passwd

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        u = User.query.filter_by(email=username).first()

        if check_credential(u):
            login_user(u)
        else:
            flash('bad command or file name')

    if current_user.is_anonymous():
        return render_template('login.html')

    return redirect(url_for("mail"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("loginpage"))

@app.route('/admin/mail/delete', methods=['POST'])
@login_required
def admin_delete():
    try:
        a = ImapAccount.query.filter_by(
            id=request.form.get('delete_id')
            ).first()

        db.session.delete(a)
        db.session.commit()

        rewrite_offlineimaprc()

        flash('deleted that email box')
    except Exception as ex:
        flash('could not delete: ' + str(ex))

    return redirect(url_for("admin_mail"))


def rewrite_offlineimaprc():
    all_mailboxes = ImapAccount.query.all()
    f = open('/home/jay/oi/offlineimaprc', 'w')

    if all_mailboxes:
        f.write(render_template('offlineimaprc.txt', mailboxes=all_mailboxes,
                email_addresses=[box.email for box in all_mailboxes]))
    else:
        f.write('')

    f.close()


@app.route('/admin/mail', methods=['GET', 'POST'])
@login_required
def admin_mail():
    def verify_imap_credential(server, email, passwd):
        import imaplib
        try:
            m = imaplib.IMAP4_SSL(request.form.get('server', ''))
            m.login(email, passwd)
            m.logout()
            return True
        except Exception as ex:
            flash("didn't work: " + str(ex))

    if request.method == 'POST':
        server = request.form.get('server')
        email = request.form.get('email')
        passwd = request.form.get('passwd')

        if verify_imap_credential(server, email, passwd):
            i = ImapAccount(server, email, passwd, current_user)
            db.session.add(i)
            db.session.commit()

            flash('horray! it worked!')

            rewrite_offlineimaprc()

    page_info = {}
    page_info['mailboxes'] = ImapAccount.query.filter_by(user_id=current_user.id).all()
    return render_template('admin_email.html', **page_info)

@app.route("/mail")
@login_required
def mail():
    page_info = {}
    page_info['mailboxes'] = ImapAccount.query.filter_by(user_id=current_user.id).all()

    page_info['r'] = {'inbox': {'subfolder': {'s3':{ }}, 's2': {}}, 'trash': {}}
    page_info['r'] = a

    return render_template('email.html', **page_info)


if __name__ == "__main__":
    db.create_all()

    # app.run()
    app.run(host='0.0.0.0', debug=True)

