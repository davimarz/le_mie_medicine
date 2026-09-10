from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import csv
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError("SECRET_KEY non configurata: imposta la variabile d'ambiente SECRET_KEY")

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'farmaci.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Farmaco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descrizione = db.Column(db.String(300), nullable=True)
    principio_attivo = db.Column(db.String(300), nullable=True)
    quantita = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.String(50), nullable=False, default='Pezzi')
    scadenza = db.Column(db.Date, nullable=False)
    aic = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class AifaCache(db.Model):
    aic = db.Column(db.String(20), primary_key=True)
    descrizione = db.Column(db.String(300))
    principio_attivo = db.Column(db.String(300))
    ditta = db.Column(db.String(150))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def password_is_valid(user, supplied_password):
    """Accetta temporaneamente anche vecchie password in chiaro e le migra al primo accesso."""
    stored = user.password or ''
    looks_hashed = stored.startswith(('scrypt:', 'pbkdf2:'))
    if looks_hashed:
        return check_password_hash(stored, supplied_password)
    if stored == supplied_password:
        user.password = generate_password_hash(supplied_password)
        db.session.commit()
        return True
    return False


@app.route('/')
def home():
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(username=username).first()
        if user and password_is_valid(user, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Credenziali errate')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if len(password) < 8:
            flash('La password deve contenere almeno 8 caratteri')
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash('Nome utente già in uso')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email già registrata')
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.commit()

        csv_path = os.path.join(basedir, 'utenti_registrati.csv')
        file_exists = os.path.isfile(csv_path)
        try:
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['Data_Registrazione', 'Username', 'Email'])
                writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), username, email])
        except Exception as e:
            print(f'Errore CSV: {e}')

        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    farmaci = Farmaco.query.filter_by(user_id=current_user.id).order_by(Farmaco.nome).all()
    aifa_count = AifaCache.query.count()

    today = datetime.now().date()
    scaduti = sum(1 for f in farmaci if f.scadenza < today)
    in_scadenza = sum(1 for f in farmaci if 0 <= (f.scadenza - today).days <= 30)

    return render_template(
        'dashboard.html',
        farmaci=farmaci,
        nome=current_user.username,
        today=today,
        aifa_count=aifa_count,
        count_scaduti=scaduti,
        count_scadenza=in_scadenza,
        count_totale=len(farmaci),
    )


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        try:
            nome = (request.form.get('nome') or '').strip()
            descrizione = (request.form.get('descrizione') or '').strip()
            principio_attivo = (request.form.get('principio_attivo') or '').strip()
            qty = max(0, int(request.form.get('quantita') or 0))
            tipo = (request.form.get('tipo') or 'Pezzi').strip()
            aic = (request.form.get('aic') or '').strip()

            scadenza_str = request.form.get('scadenza') or ''
            year, month = map(int, scadenza_str.split('-'))
            last_day = calendar.monthrange(year, month)[1]
            scad_date = datetime(year, month, last_day).date()

            if not nome:
                raise ValueError('Il nome del farmaco è obbligatorio')

            nuovo = Farmaco(
                nome=nome,
                descrizione=descrizione,
                principio_attivo=principio_attivo,
                quantita=qty,
                tipo=tipo,
                scadenza=scad_date,
                aic=aic,
                user_id=current_user.id,
            )
            db.session.add(nuovo)
            db.session.commit()
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Errore dati: {e}')
    return render_template('add.html')


@app.route('/api/update_qty_direct', methods=['POST'])
@login_required
def update_qty_direct():
    data = request.get_json(silent=True) or {}
    farmaco = db.session.get(Farmaco, data.get('id')) if data.get('id') is not None else None
    if farmaco and farmaco.user_id == current_user.id:
        try:
            farmaco.quantita = max(0, int(data.get('qty', 0)))
            db.session.commit()
            return jsonify({'success': True, 'qty': farmaco.quantita})
        except (TypeError, ValueError):
            db.session.rollback()
    return jsonify({'success': False}), 400


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    farmaco = db.session.get(Farmaco, id)
    if not farmaco:
        flash('Farmaco non trovato')
    elif farmaco.user_id == current_user.id:
        db.session.delete(farmaco)
        db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/update_aifa_db')
@login_required
def update_aifa_db():
    file_path = os.path.join(basedir, 'confezioni.csv')
    if not os.path.exists(file_path):
        flash("File 'confezioni.csv' non trovato sul server")
        return redirect(url_for('dashboard'))

    try:
        AifaCache.query.delete()
        db.session.commit()

        with open(file_path, 'r', encoding='latin-1', errors='replace') as f:
            csv_input = csv.DictReader(f, delimiter=';')
            if not csv_input.fieldnames or 'codice_aic' not in csv_input.fieldnames:
                f.seek(0)
                csv_input = csv.DictReader(f, delimiter=',')

            count = 0
            batch = []
            for row in csv_input:
                raw_aic = (row.get('codice_aic') or '').strip()
                if raw_aic.isdigit():
                    raw_aic = raw_aic.zfill(9)

                nome_commerciale = (row.get('denominazione') or '').strip()
                desc_completa = f"{row.get('denominazione', '')} {row.get('descrizione', '')}".strip()
                ditta = (row.get('ragione_sociale') or '').strip()
                pa = (row.get('pa_associati') or row.get('principio_attivo') or '').strip()

                if raw_aic and nome_commerciale:
                    batch.append(AifaCache(
                        aic=raw_aic,
                        descrizione=desc_completa[:300],
                        principio_attivo=pa[:300],
                        ditta=ditta[:150],
                    ))
                    count += 1
                    if len(batch) >= 1000:
                        db.session.bulk_save_objects(batch)
                        db.session.commit()
                        batch = []
            if batch:
                db.session.bulk_save_objects(batch)
                db.session.commit()

        flash(f'Aggiornamento completato: importati {count} farmaci')
    except Exception as e:
        db.session.rollback()
        flash(f'Errore tecnico durante l’aggiornamento AIFA: {e}')
    return redirect(url_for('dashboard'))


@app.route('/api/get_farmaco/<codice>')
@login_required
def api_get_farmaco(codice):
    codice = codice.strip().upper()
    if codice.startswith('A') and codice[1:].isdigit():
        codice = codice[1:]

    farmaco = AifaCache.query.filter_by(aic=codice).first()
    if not farmaco and len(codice) == 8 and codice.isdigit():
        farmaco = AifaCache.query.filter_by(aic='0' + codice).first()
    if not farmaco and codice.startswith('0'):
        farmaco = AifaCache.query.filter_by(aic=codice[1:]).first()

    if farmaco:
        return jsonify({
            'success': True,
            'aic': farmaco.aic,
            'nome': farmaco.descrizione,
            'principio_attivo': farmaco.principio_attivo,
            'ditta': farmaco.ditta,
        })
    return jsonify({'success': False})


with app.app_context():
    db.create_all()
