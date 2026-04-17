from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'change-me-please'
DB = 'app.db'
PER_PAGE = 10
STATUSES = ['новое', 'в работе', 'выполнено']
CHOICES = ['Вариант A', 'Вариант B', 'Вариант C']


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nickname TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fio TEXT, phone TEXT, email TEXT, dt TEXT,
            field1 TEXT, field2 TEXT, field3 TEXT,
            choice TEXT,
            status TEXT DEFAULT 'новое',
            answer TEXT DEFAULT '',
            created_at TEXT
        );
        ''')
        if not c.execute("SELECT 1 FROM users WHERE email='admin@admin'").fetchone():
            c.execute("INSERT INTO users(email,nickname,password,is_admin) VALUES(?,?,?,1)",
                      ('admin@admin', 'admin', generate_password_hash('admin')))


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not session.get('is_admin'):
            abort(403)
        return f(*a, **kw)
    return w


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        nickname = request.form['nickname'].strip()
        pw = request.form['password']
        if not email or not nickname or not pw:
            flash('Заполните все поля')
            return redirect(url_for('register'))
        try:
            with db() as c:
                c.execute("INSERT INTO users(email,nickname,password) VALUES(?,?,?)",
                          (email, nickname, generate_password_hash(pw)))
            flash('Регистрация успешна, войдите')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email или никнейм уже заняты')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        pw = request.form['password']
        with db() as c:
            u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and check_password_hash(u['password'], pw):
            session['uid'] = u['id']
            session['email'] = u['email']
            session['nickname'] = u['nickname']
            session['is_admin'] = bool(u['is_admin'])
            return redirect(url_for('admin' if u['is_admin'] else 'cabinet'))
        flash('Неверный email или пароль')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/cabinet')
@login_required
def cabinet():
    page = max(1, int(request.args.get('page', 1)))
    with db() as c:
        total = c.execute("SELECT COUNT(*) FROM requests WHERE user_id=?",
                          (session['uid'],)).fetchone()[0]
        rows = c.execute("SELECT * FROM requests WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                         (session['uid'], PER_PAGE, (page - 1) * PER_PAGE)).fetchall()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template('cabinet.html', rows=rows, page=page, pages=pages)


@app.route('/cabinet/new', methods=['GET', 'POST'])
@login_required
def new_request():
    if request.method == 'POST':
        f = request.form
        with db() as c:
            c.execute('''INSERT INTO requests(user_id,fio,phone,email,dt,field1,field2,field3,choice,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)''',
                      (session['uid'], f.get('fio'), f.get('phone'), f.get('email'),
                       f.get('dt'), f.get('field1'), f.get('field2'), f.get('field3'),
                       f.get('choice'), datetime.now().strftime('%Y-%m-%d %H:%M')))
        return redirect(url_for('cabinet'))
    return render_template('new_request.html', choices=CHOICES)


@app.route('/admin')
@login_required
@admin_required
def admin():
    page = max(1, int(request.args.get('page', 1)))
    status = request.args.get('status', '')
    q = request.args.get('q', '').strip()
    where, params = [], []
    if status in STATUSES:
        where.append("status=?"); params.append(status)
    if q:
        where.append("(fio LIKE ? OR phone LIKE ? OR email LIKE ?)")
        params += [f'%{q}%'] * 3
    wsql = ('WHERE ' + ' AND '.join(where)) if where else ''
    with db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM requests {wsql}", params).fetchone()[0]
        rows = c.execute(f"SELECT * FROM requests {wsql} ORDER BY id DESC LIMIT ? OFFSET ?",
                         params + [PER_PAGE, (page - 1) * PER_PAGE]).fetchall()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return render_template('admin.html', rows=rows, page=page, pages=pages,
                           status=status, q=q, statuses=STATUSES)


@app.route('/admin/update/<int:rid>', methods=['POST'])
@login_required
@admin_required
def update_request(rid):
    s = request.form.get('status')
    answer = request.form.get('answer', '').strip()
    with db() as c:
        if s in STATUSES:
            c.execute("UPDATE requests SET status=?, answer=? WHERE id=?", (s, answer, rid))
        else:
            c.execute("UPDATE requests SET answer=? WHERE id=?", (answer, rid))
    return redirect(request.referrer or url_for('admin'))


if __name__ == '__main__':
    if not os.path.exists(DB):
        init_db()
    app.run(debug=True)
