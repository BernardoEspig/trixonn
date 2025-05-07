from flask import Blueprint, Flask, render_template, request, redirect, url_for, flash, session
import re
import hashlib
import uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import mailtrap as mt
import psycopg2
from psycopg2.extras import DictCursor

login_bp = Blueprint('login', __name__)


# Configuração do Banco de Dados
def get_db_connection():
    return psycopg2.connect(
        host="dpg-d0db24k9c44c73ca2ljg-a",  # substitua pelo hostname real do Render
        database="trixonn_postgres",       # substitua pelo nome do banco do Render
        user="trixonn_postgres_user",             # substitua pelo usuário do banco
        password="aPGDtngvRy3KEYo7Ofow4xoURyuK8VY9",          # substitua pela senha
        port="5432"
    )


# Configuração do Mailtrap (para testes)
MAILTRAP_API_KEY = "1ce85fdc49d47bd017b54101bafa83a3"


# Helpers de segurança
def create_session(user_id, device_info):
    """Cria sessão sem depender de expires_at"""
    session_id = str(uuid.uuid4())
    access_hash = hashlib.sha256(f"{user_id}{datetime.now()}".encode()).hexdigest()

    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("""
            INSERT INTO user_sessions 
            (session_id, user_id, device_info, access_hash, is_active) 
            VALUES (%s, %s, %s, %s, TRUE)
        """, (session_id, user_id, device_info, access_hash))

        db.commit()
        return session_id, access_hash
    except Exception as e:
        print(f"Erro ao criar sessão: {e}")
        raise
    finally:
        cursor.close()
        db.close()

def verify_session():
    """Versão simplificada que funciona sem expires_at"""
    if 'user_id' not in session or 'access_hash' not in session:
        return False

    db = get_db_connection()
    cursor = db.cursor(cursor_factory=DictCursor)

    try:
        # Versão simplificada - remove a verificação de expires_at
        cursor.execute("""
            SELECT * FROM user_sessions 
            WHERE user_id = %s 
            AND access_hash = %s
            AND is_active = TRUE
        """, (session['user_id'], session['access_hash']))

        return cursor.fetchone() is not None
    except Exception as e:
        print(f"Erro na verificação de sessão: {e}")
        return False
    finally:
        cursor.close()
        db.close()

# Rotas de autenticação
@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('senha')

        if not email or not password:
            flash('Preencha todos os campos', 'error')
            return redirect(url_for('login.login'))

        db = get_db_connection()
        cursor = db.cursor(cursor_factory=DictCursor)

        try:
            cursor.execute("SELECT id, nome, senha FROM cadastro_usuario WHERE email = %s", (email,))
            user = cursor.fetchone()

            if not user:
                flash('Credenciais inválidas', 'error')
                return redirect(url_for('login.login'))

            # Verificação compatível (aceita senha em texto plano OU hash)
            if password == user['senha'] or check_password_hash(user['senha'], password):
                session_id, access_hash = create_session(user['id'], request.headers.get('User-Agent'))
                session['user_id'] = user['id']
                session['user_name'] = user['nome']
                session['access_hash'] = access_hash

                # Vinculação automática (nova parte)
                cursor.execute("""
                    UPDATE empresa_usuarios
                    SET usuario_id = %s
                    WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
                    AND usuario_id IS NULL
                """, (user['id'], email))

                cursor.execute("""
                    WITH source_data AS (
                        SELECT 
                            %s AS user_id,
                            eu.empresa_id,
                            eu.vinculo,
                            e.nome_empresa,
                            e.segmento
                        FROM empresa_usuarios eu
                        JOIN empresas e ON eu.empresa_id = e.id
                        WHERE eu.email = %s
                    )
                    INSERT INTO dados_usuario (user_id, empresa_id, vinculo, empresa, segmento)
                    SELECT * FROM source_data
                    ON CONFLICT (user_id) DO UPDATE SET
                        empresa_id = EXCLUDED.empresa_id,
                        vinculo = EXCLUDED.vinculo
                    WHERE NOT EXISTS (
                        SELECT 1 FROM dados_usuario WHERE user_id = %s
                    )
                """, (user['id'], email, user['id']))

                db.commit()
                flash('Login bem-sucedido!', 'success')
                return redirect(url_for('user_page_bp.user_page'))

            flash('Credenciais inválidas', 'error')
            return redirect(url_for('login.login'))

        except Exception as e:
            print(f"Erro no login: {e}")
            flash('Erro no sistema', 'error')
            return redirect(url_for('login.login'))
        finally:
            cursor.close()
            db.close()

    return render_template('login.html')


@login_bp.route('/show_recovery', methods=['POST'])
def show_recovery():
    return render_template('login.html', show_recovery=True)


# Middleware de segurança
@login_bp.before_request
def protect_views():
    allowed_routes = [
        'login.login',
        'login.logout',
        'login.forgot_password',
        'login.reset_password',
        'login.show_recovery',
        'static'
    ]
    if request.endpoint not in allowed_routes:
        if not verify_session():
            return redirect(url_for('login.login'))


# Rotas protegidas
@login_bp.route('/user_page')
def user_page():
    if not verify_session():
        return redirect(url_for('login.login'))  # Corrige a rota caso esteja com Blueprint

    user_name = session.get('user_name', 'Usuário')
    return render_template('user_page.html', user_name=user_name)


# --- SISTEMA DE RECUPERAÇÃO --- #

@login_bp.route('/forgot_password', methods=['POST'])
def forgot_password():
    email = request.form['email']

    with get_db_connection() as db:
        cursor = db.cursor(cursor_factory=DictCursor)

        # Verifica se o usuário existe
        cursor.execute("SELECT id FROM cadastro_usuario WHERE email = %s", (email,))
        if not cursor.fetchone():
            flash('Se o email existir, enviaremos um link', 'info')
            return redirect(url_for('login'))

        # Gera token único
        token = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=1)

        # Remove tokens antigos e insere novo
        cursor.execute(
            "DELETE FROM password_reset_tokens WHERE user_id = (SELECT id FROM cadastro_usuario WHERE email = %s)",
            (email,))
        cursor.execute("""
            INSERT INTO password_reset_tokens 
            (token_hash, user_id, expires_at) 
            VALUES (%s, (SELECT id FROM cadastro_usuario WHERE email = %s), %s)
        """, (hashlib.sha256(token.encode()).hexdigest(), email, expires_at))
        db.commit()

        # Debug: Mostra o link no console
        reset_link = f"http://localhost:5000/reset_password?token={token}"
        print(f"🔑 Link de recuperação: {reset_link}")

    flash('Se o email existir, enviaremos um link', 'info')
    return redirect(url_for('login'))


@login_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        token = request.args.get('token')
        if not token:
            return redirect(url_for('login'))

        with get_db_connection() as db:
            cursor = db.cursor()
            cursor.execute("""
                SELECT 1 FROM password_reset_tokens 
                WHERE token_hash = %s 
                AND used = FALSE 
                AND expires_at > NOW()
            """, (hashlib.sha256(token.encode()).hexdigest(),))

            if not cursor.fetchone():
                flash('Link inválido ou expirado', 'error')
                return redirect(url_for('login'))

        return render_template('reset_password.html', token=token)

    else:  # POST
        token = request.form['token']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Validações básicas
        if new_password != confirm_password:
            flash('As senhas não coincidem', 'error')
            return redirect(url_for('reset_password', token=token))

        if len(new_password) < 8:
            flash('Senha muito curta (mínimo 8 caracteres)', 'error')
            return redirect(url_for('reset_password', token=token))

        with get_db_connection() as db:
            cursor = db.cursor(cursor_factory=DictCursor)

            # Verifica token válido
            cursor.execute("""
                SELECT user_id FROM password_reset_tokens 
                WHERE token_hash = %s 
                AND used = FALSE 
                AND expires_at > NOW()
                FOR UPDATE
            """, (hashlib.sha256(token.encode()).hexdigest(),))

            token_data = cursor.fetchone()
            if not token_data:
                flash('Link inválido ou expirado', 'error')
                return redirect(url_for('login'))

            # Atualiza senha
            cursor.execute("""
                UPDATE cadastro_usuario 
                SET senha = %s 
                WHERE id = %s
            """, (generate_password_hash(new_password), token_data['user_id']))

            # Marca token como usado
            cursor.execute("""
                UPDATE password_reset_tokens 
                SET used = TRUE 
                WHERE token_hash = %s
            """, (hashlib.sha256(token.encode()).hexdigest(),))

            db.commit()

        flash('Senha alterada com sucesso! Faça login', 'success')
        return redirect(url_for('login'))


