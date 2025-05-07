from flask import Blueprint, Flask, render_template, request, redirect, url_for, flash
import re  # Para validar a senha com regex
import psycopg2
from flask import Blueprint
import psycopg2
from psycopg2.extras import DictCursor

cadastro_usuario_bp = Blueprint('cadastro_usuario_bp', __name__)

# Configuração do MySQL (substitua com seus dados)

def get_db_connection():
    return psycopg2.connect(
        host="postgresql://trixonn_postgres_user:aPGDtngvRy3KEYo7Ofow4xoURyuK8VY9@dpg-d0db24k9c44c73ca2ljg-a/trixonn_postgres",  # substitua pelo hostname real do Render
        database="trixonn_postgres",       # substitua pelo nome do banco do Render
        user="trixonn_postgres_user",             # substitua pelo usuário do banco
        password="aPGDtngvRy3KEYo7Ofow4xoURyuK8VY9",          # substitua pela senha
        port="5432"
    )


# Rota para a página de registro
# Em cadastro_usuario.py, modifique a rota registrar()

@cadastro_usuario_bp.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email'].strip().lower()  # Normaliza o email
        senha = request.form['senha']

        # Validação da senha (regex: 1 maiúscula, 1 número e caracteres especiais)
        if not (re.search(r'[A-Z]', senha) and  # Pelo menos 1 maiúscula
                re.search(r'\d', senha) and  # Pelo menos 1 número
                re.search(r'[@#$%!\-_]', senha)):  # Pelo menos 1 caractere especial
            flash('Senha deve ter 1 maiúscula, 1 número e 1 destes: @#$%!_-', 'erro')
            return redirect(url_for('cadastro_usuario_bp.registrar'))

        db = get_db_connection()
        cursor = db.cursor()
        try:
            # Verifica se email já existe
            cursor.execute("SELECT email FROM cadastro_usuario WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Email já cadastrado!', 'erro')
                return redirect(url_for('cadastro_usuario_bp.registrar'))

            # Insere o novo usuário com senha hasheada
            cursor.execute(
                "INSERT INTO cadastro_usuario (nome, email, senha) VALUES (%s, %s, %s)",
                (nome, email, senha)  # Agora com hash
            )
            user_id = cursor.lastrowid

            # 1. Atualiza empresa_usuarios com o user_id
            cursor.execute("""
                UPDATE empresa_usuarios
                SET usuario_id = %s
                WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
                AND usuario_id IS NULL
            """, (user_id, email))

            # 2. Preenche dados_usuario com todas as informações
            cursor.execute("""
                INSERT INTO dados_usuario (user_id, empresa_id, vinculo, empresa, segmento)
                SELECT 
                    %s,
                    eu.empresa_id,
                    eu.vinculo,
                    e.nome_empresa,
                    e.segmento
                FROM empresa_usuarios eu
                JOIN empresas e ON eu.empresa_id = e.id
                WHERE eu.email = %s
                ON CONFLICT (user_id) DO UPDATE SET
                    empresa_id = EXCLUDED.empresa_id,
                    vinculo = EXCLUDED.vinculo,
                    empresa = EXCLUDED.empresa,
                    segmento = EXCLUDED.segmento
            """, (user_id, email))

            db.commit()
            flash('Cadastro realizado com sucesso!', 'success')
            return redirect(url_for('login.login'))

        except Exception as e:
            db.rollback()
            print(f"Erro durante o registro: {str(e)}")
            flash(f'Erro durante o registro: {str(e)}', 'error')
            return redirect(url_for('cadastro_usuario_bp.registrar'))
        finally:
            cursor.close()
            db.close()

    return render_template('registrar.html')
# Rota fictícia para login (você implementará depois)
@cadastro_usuario_bp.route('/login')
def login_user():
    return render_template('login.html')
