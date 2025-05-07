from flask import Flask
from login import login_bp
from cadastro_usuario import cadastro_usuario_bp
from user_page import user_page_bp
from introducao import introducao_bp
import os
import psycopg2
from psycopg2.extras import DictCursor
app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_segura'

# Configurações de upload
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['CERTIFICADOS_FOLDER'] = os.path.join('static', 'certificados')
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls'}
app.config['CERTIFICADOS_ALLOWED_EXTENSIONS'] = {'pdf'}

# Criar pastas necessárias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CERTIFICADOS_FOLDER'], exist_ok=True)

# Registro dos blueprints
app.register_blueprint(login_bp)
app.register_blueprint(cadastro_usuario_bp)
app.register_blueprint(user_page_bp)
app.register_blueprint(introducao_bp)

# Configuração do Banco de Dados
def get_db_connection():
    return psycopg2.connect(
        host="postgresql://trixonn_postgres_user:aPGDtngvRy3KEYo7Ofow4xoURyuK8VY9@dpg-d0db24k9c44c73ca2ljg-a/trixonn_postgres",  # substitua pelo hostname real do Render
        database="trixonn_postgres",       # substitua pelo nome do banco do Render
        user="trixonn_postgres_user",             # substitua pelo usuário do banco
        password="aPGDtngvRy3KEYo7Ofow4xoURyuK8VY9",          # substitua pela senha
        port="5432"
    )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        with open('schema.sql', 'r') as f:
            sql_script = f.read()
            cursor.execute(sql_script)
        conn.commit()
        print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar banco de dados: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Chame esta função no início da sua aplicação
init_db()

if __name__ == '__main__':
    with app.app_context():
        from user_page import vincular_usuarios_automaticamente
        vincular_usuarios_automaticamente()
    app.run(host='0.0.0.0', port=5000, debug=True)