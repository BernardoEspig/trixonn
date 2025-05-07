from flask import Flask
from login import login_bp
from cadastro_usuario import cadastro_usuario_bp
from user_page import user_page_bp
from introducao import introducao_bp
import os

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

if __name__ == '__main__':
    with app.app_context():
        from user_page import vincular_usuarios_automaticamente
        vincular_usuarios_automaticamente()
    app.run(host='0.0.0.0', port=5000, debug=True)