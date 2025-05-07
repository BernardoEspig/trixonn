from flask import jsonify, current_app, Blueprint, Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
import uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
import json  # Adicione esta linha no início do arquivo
import pandas as pd
from werkzeug.utils import secure_filename
import os

user_page_bp = Blueprint('user_page_bp', __name__)

# Configuração do Banco de Dados
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="db"
    )

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def atualizar_dados_empresa(user_id):
    """Atualiza automaticamente os dados da empresa no perfil do usuário"""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE dados_usuario du
            JOIN empresas e ON du.empresa_id = e.id
            SET 
                du.empresa = e.nome_empresa,
                du.vinculo = 'Funcionário',
                du.segmento = e.segmento
            WHERE du.user_id = %s
        """, (user_id,))
        db.commit()
    except Exception as e:
        print(f"Erro ao atualizar dados da empresa: {e}")
    finally:
        cursor.close()
        db.close()


def vincular_usuario_existente(user_id, email):
    """Vincula um usuário existente às empresas cadastradas"""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Atualiza empresa_usuarios
        cursor.execute("""
            UPDATE empresa_usuarios
            SET usuario_id = %s
            WHERE LOWER(TRIM(email)) = LOWER(TRIM(%s))
            AND usuario_id IS NULL
        """, (user_id, email))

        # 2. Atualiza dados_usuario
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
            WHERE eu.usuario_id = %s
            ON DUPLICATE KEY UPDATE
                empresa_id = VALUES(empresa_id),
                vinculo = VALUES(vinculo),
                empresa = VALUES(empresa),
                segmento = VALUES(segmento)
        """, (user_id, user_id))

        db.commit()
    except Exception as e:
        print(f"Erro ao vincular usuário existente: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()


def vincular_usuarios_automaticamente():
    """Vincula automaticamente usuários cadastrados aos seus dados de empresa"""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Atualiza empresa_usuarios com os IDs corretos
        cursor.execute("""
            UPDATE empresa_usuarios eu
            JOIN cadastro_usuario cu ON LOWER(TRIM(eu.email)) = LOWER(TRIM(cu.email))
            SET eu.usuario_id = cu.id
            WHERE eu.usuario_id IS NULL
        """)

        # 2. Atualiza dados_usuario com informações da empresa
        cursor.execute("""
            INSERT INTO dados_usuario (user_id, empresa_id, vinculo, empresa, segmento)
            SELECT 
                eu.usuario_id,
                eu.empresa_id,
                eu.vinculo,
                e.nome_empresa,
                e.segmento
            FROM empresa_usuarios eu
            JOIN empresas e ON eu.empresa_id = e.id
            WHERE eu.usuario_id IS NOT NULL
            ON DUPLICATE KEY UPDATE
                empresa_id = VALUES(empresa_id),
                vinculo = VALUES(vinculo),
                empresa = VALUES(empresa),
                segmento = VALUES(segmento)
        """)

        db.commit()
        print("Usuários vinculados automaticamente com sucesso")
    except Exception as e:
        print(f"Erro ao vincular usuários automaticamente: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()

def vincular_usuario_empresa(user_id, empresa_id):
    """Vincula um usuário a uma empresa na tabela dados_usuario"""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO dados_usuario 
            (user_id, empresa_id) 
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE empresa_id = VALUES(empresa_id)
        """, (user_id, empresa_id))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Erro ao vincular usuário à empresa: {str(e)}")
    finally:
        cursor.close()
        db.close()

def sincronizar_vinculos():
    """Sincroniza os vínculos entre empresa_usuarios e dados_usuario"""
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE dados_usuario du
            JOIN cadastro_usuario cu ON du.user_id = cu.id
            JOIN empresa_usuarios eu ON cu.email = eu.email
            SET 
                du.vinculo = eu.vinculo,
                du.empresa_id = eu.empresa_id,
                du.empresa = (SELECT nome_empresa FROM empresas WHERE id = eu.empresa_id)
            WHERE du.vinculo != eu.vinculo OR du.vinculo IS NULL
        """)
        db.commit()
        print(f"{cursor.rowcount} vínculos atualizados")
    except Exception as e:
        print(f"Erro na sincronização: {e}")
    finally:
        cursor.close()
        db.close()


# Adicione esta função para sincronizar os usuários
def sincronizar_usuarios_empresa():
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Atualiza usuario_id na empresa_usuarios
        cursor.execute("""
            UPDATE empresa_usuarios eu
            JOIN cadastro_usuario cu ON LOWER(TRIM(eu.email)) = LOWER(TRIM(cu.email))
            SET eu.usuario_id = cu.id
            WHERE eu.usuario_id IS NULL
        """)

        # Cria/atualiza registros em dados_usuario
        cursor.execute("""
            INSERT INTO dados_usuario (user_id, empresa_id, vinculo, empresa, segmento)
            SELECT 
                eu.usuario_id,
                eu.empresa_id,
                eu.vinculo,
                e.nome_empresa,
                e.segmento
            FROM empresa_usuarios eu
            JOIN empresas e ON eu.empresa_id = e.id
            WHERE eu.usuario_id IS NOT NULL
            ON DUPLICATE KEY UPDATE
                empresa_id = VALUES(empresa_id),
                vinculo = VALUES(vinculo),
                empresa = VALUES(empresa),
                segmento = VALUES(segmento)
        """)

        db.commit()
        print("Sincronização de usuários concluída")
    except Exception as e:
        print(f"Erro na sincronização: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()

# Helpers de segurança
def create_session(user_id, device_info):
    """Cria uma nova sessão no banco de dados"""
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
    finally:
        cursor.close()
        db.close()


def verify_session():
    """Verifica se a sessão é válida"""
    if 'user_id' not in session or 'access_hash' not in session:
        return False

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM user_sessions 
            WHERE user_id = %s AND access_hash = %s AND is_active = TRUE
        """, (session['user_id'], session['access_hash']))
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        db.close()


# Middleware de segurança
@user_page_bp.before_request
def protect_views():
    allowed_routes = ['login', 'static', 'forgot_password', 'reset_password', 'documentacoes', 'logout']
    if request.endpoint not in allowed_routes and not verify_session():
        return redirect(url_for('login'))


@user_page_bp.route('/login', methods=['GET', 'POST'])
def login():
    return redirect(url_for('login.login'))

@user_page_bp.route('/logout')
def logout():
    """Encerra a sessão completamente"""
    if 'user_id' in session:
        db = get_db_connection()
        cursor = db.cursor()
        try:
            cursor.execute("""
                UPDATE user_sessions 
                SET is_active = FALSE 
                WHERE user_id = %s AND access_hash = %s
            """, (session['user_id'], session['access_hash']))
            db.commit()
        finally:
            cursor.close()
            db.close()

    session.clear()
    return redirect(url_for('login.login'))


# Rotas principais
@user_page_bp.route('/user_page')
def user_page():
    print("Sessão atual:", dict(session))  # Mostra tudo
    user_name = session.get('user_name', 'Usuário')
    return render_template('user_page.html', user_name=user_name)


@user_page_bp.route('/user_profile', methods=['GET', 'POST'])
def user_profile():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']

    if request.method == 'POST':
        db = get_db_connection()
        try:
            cursor = db.cursor()
            centro_trabalho = request.form.get('centro_trabalho')
            contato = request.form.get('contato')

            # Verifica se já existe registro
            cursor.execute("SELECT 1 FROM dados_usuario WHERE user_id = %s", (user_id,))
            existe_registro = cursor.fetchone()

            if existe_registro:
                # ATUALIZA registro existente
                cursor.execute("""
                    UPDATE dados_usuario 
                    SET centro_trabalho = %s,
                        contato = %s
                    WHERE user_id = %s
                """, (centro_trabalho, contato, user_id))
            else:
                # INSERE novo registro apenas se não existir
                cursor.execute("""
                    INSERT INTO dados_usuario 
                    (user_id, centro_trabalho, contato)
                    VALUES (%s, %s, %s)
                """, (user_id, centro_trabalho, contato))

            db.commit()
            flash('Perfil atualizado com sucesso!', 'success')
            return redirect(url_for('user_page_bp.user_profile'))
        except Exception as e:
            print(f"Erro ao atualizar perfil: {e}")
            db.rollback()
            flash('Erro ao atualizar perfil', 'error')
            return redirect(url_for('user_page_bp.user_profile'))
        finally:
            cursor.close()
            db.close()

    # Processar GET
    db = get_db_connection()
    try:
        cursor = db.cursor(dictionary=True)

        # Consulta otimizada que busca todos os dados necessários
        cursor.execute("""
            SELECT 
                du.centro_trabalho,
                du.contato,
                COALESCE(eu.vinculo, du.vinculo, 'Funcionário') AS vinculo,
                COALESCE(e.nome_empresa, 'Não atribuído') AS empresa,
                COALESCE(e.segmento, 'Não especificado') AS segmento,
                cu.nome,
                cu.email
            FROM cadastro_usuario cu
            LEFT JOIN dados_usuario du ON cu.id = du.user_id
            LEFT JOIN empresa_usuarios eu ON cu.id = eu.usuario_id
            LEFT JOIN empresas e ON (du.empresa_id = e.id OR eu.empresa_id = e.id)
            WHERE cu.id = %s
            LIMIT 1
        """, (user_id,))

        result = cursor.fetchone() or {}

        # Debug - remover após testes
        print(f"Dados encontrados para user_id {user_id}: {result}")

        profile_data = {
            'centro_trabalho': result.get('centro_trabalho'),
            'contato': result.get('contato'),
            'vinculo': result.get('vinculo'),
            'empresa': result.get('empresa'),
            'segmento': result.get('segmento')
        }

        user_data = {
            'nome': result.get('nome'),
            'email': result.get('email')
        }

        centros_trabalho = ['AUT-GER1', 'ELE-GER1', 'MEC-GER1']

        return render_template('user_profile.html',
                               user_data=user_data,
                               profile_data=profile_data,
                               centros_trabalho=centros_trabalho)

    except Exception as e:
        print(f"Erro ao buscar perfil: {e}")
        flash('Erro ao carregar perfil', 'error')
        return redirect(url_for('user_page_bp.user_page'))
    finally:
        cursor.close()
        db.close()




# Adicione estas funções de apoio no início do arquivo
def get_usuarios_disponiveis():
    """Retorna todos os usuários para seleção como responsáveis"""
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT u.id, u.nome, d.centro_trabalho 
            FROM cadastro_usuario u
            LEFT JOIN dados_usuario d ON u.id = d.user_id
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        db.close()


# Atualize a rota cadastrar_empresa para:
@user_page_bp.route('/cadastrar_empresa', methods=['GET', 'POST'])
def cadastrar_empresa():
    if not verify_session():
        return redirect(url_for('login.login'))

    if request.method == 'POST':
        try:
            print("\n=== INÍCIO DO PROCESSAMENTO ===")  # Debug

            # Processar arquivo Excel
            usuarios_importados = []
            if 'arquivo_usuarios' in request.files:
                file = request.files['arquivo_usuarios']
                if file and file.filename != '':
                    print(f"Arquivo recebido: {file.filename}")  # Debug
                    try:
                        df = pd.read_excel(file.stream)
                        print("Planilha lida com sucesso")  # Debug
                        if all(col in df.columns for col in ['nome', 'email', 'vinculo']):  # Alterado para verificar 'vinculo'
                            usuarios_importados = df.to_dict('records')
                            print(f"{len(usuarios_importados)} usuários importados")  # Debug
                        else:
                            print("Colunas faltando no Excel (necessário: nome, email, vinculo)")  # Debug
                            flash('O arquivo Excel deve conter as colunas: nome, email e vinculo', 'error')
                            return redirect(url_for('user_page_bp.cadastrar_empresa'))
                    except Exception as e:
                        print(f"Erro ao ler Excel: {str(e)}")  # Debug
                        flash('Erro ao processar o arquivo Excel', 'error')
                        return redirect(url_for('user_page_bp.cadastrar_empresa'))

            # Coletar dados do formulário
            form_data = {k: v.strip() if isinstance(v, str) else v for k, v in request.form.items()}
            print("Dados do formulário:", form_data)  # Debug

            # Validar campos obrigatórios
            required_fields = ['nome_empresa', 'razao_social', 'cnpj', 'centro_trabalho',
                               'segmento', 'email_coorporativo', 'tipo_empresa']
            if any(not form_data.get(field) for field in required_fields):
                flash('Preencha todos os campos obrigatórios', 'error')
                return redirect(url_for('user_page_bp.cadastrar_empresa'))

            # Conexão com o banco de dados
            db = get_db_connection()
            cursor = db.cursor(dictionary=True)

            try:
                print("Inserindo empresa no banco...")  # Debug
                # Inserir empresa
                cursor.execute("""
                    INSERT INTO empresas (
                        nome_empresa, razao_social, cnpj, centro_trabalho, segmento,
                        email_coorporativo, contato, tipo_empresa, criado_por
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    form_data['nome_empresa'],
                    form_data['razao_social'],
                    form_data['cnpj'],
                    form_data['centro_trabalho'],
                    form_data['segmento'],
                    form_data['email_coorporativo'],
                    form_data.get('contato', ''),
                    form_data['tipo_empresa'],
                    session['user_id']
                ))
                empresa_id = cursor.lastrowid
                print(f"Empresa inserida com ID: {empresa_id}")  # Debug

                # Inserir usuários importados
                if usuarios_importados:
                    print("Inserindo usuários importados...")  # Debug
                    for usuario in usuarios_importados:
                        try:
                            email = usuario.get('email', '').strip().lower()
                            vinculo = usuario.get('vinculo', 'Funcionário').strip()

                            # 1. Insere/atualiza na empresa_usuarios
                            cursor.execute("""
                                INSERT INTO empresa_usuarios 
                                (empresa_id, nome, email, vinculo)
                                VALUES (%s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    nome = VALUES(nome),
                                    vinculo = VALUES(vinculo)
                            """, (
                                empresa_id,
                                usuario.get('nome', '').strip(),
                                email,
                                vinculo
                            ))

                            # 2. Atualiza usuario_id se o usuário existir
                            cursor.execute("""
                                UPDATE empresa_usuarios eu
                                JOIN cadastro_usuario cu ON LOWER(TRIM(cu.email)) = %s
                                SET eu.usuario_id = cu.id
                                WHERE eu.email = %s AND eu.empresa_id = %s
                            """, (email, email, empresa_id))

                            print(f"Usuário {email} inserido/atualizado")  # Debug

                        except mysql.connector.Error as err:
                            print(f"Erro ao inserir usuário {email}: {err}")  # Debug
                            if err.errno != 1062:  # Ignora duplicatas
                                raise

                    # Chama a sincronização após importar todos os usuários
                    #sincronizar_usuarios_empresa()

                # Processar responsáveis (mantido igual)
                responsaveis_emails = [e.strip() for e in form_data.get('responsaveis_emails', '').split(',') if e.strip()]
                if responsaveis_emails:
                    print("Processando responsáveis:", responsaveis_emails)  # Debug
                    responsaveis_info = []
                    for email in responsaveis_emails:
                        # Verifica usuários existentes
                        cursor.execute("SELECT id, nome FROM cadastro_usuario WHERE email = %s", (email,))
                        if user := cursor.fetchone():
                            responsaveis_info.append({
                                'tipo': 'usuario',
                                'id': user['id'],
                                'email': email,
                                'nome': user['nome']
                            })
                        else:
                            # Verifica usuários importados
                            cursor.execute("""
                                SELECT id, nome FROM empresa_usuarios 
                                WHERE email = %s AND empresa_id = %s
                            """, (email, empresa_id))
                            if imported_user := cursor.fetchone():
                                responsaveis_info.append({
                                    'tipo': 'importado',
                                    'id': imported_user['id'],
                                    'email': email,
                                    'nome': imported_user['nome']
                                })

                    # Atualiza empresa com responsáveis
                    if responsaveis_info:
                        cursor.execute("""
                            UPDATE empresas 
                            SET responsaveis = %s 
                            WHERE id = %s
                        """, (json.dumps(responsaveis_info), empresa_id))
                        print("Responsáveis atualizados")  # Debug

                db.commit()
                print("Commit realizado com sucesso!")  # Debug
                # Chame esta função após importar o Excel ou no início do app
                sincronizar_usuarios_empresa()
                vincular_usuario_empresa(session['user_id'], empresa_id)

                flash('Empresa cadastrada com sucesso!', 'success')
                return redirect(url_for('user_page_bp.empresa'))

            except mysql.connector.Error as err:
                db.rollback()
                print(f"Erro no banco de dados: {err}")  # Debug
                if err.errno == 1062:
                    flash('CNPJ já cadastrado no sistema', 'error')
                else:
                    flash(f'Erro ao cadastrar empresa: {str(err)}', 'error')
                return redirect(url_for('user_page_bp.cadastrar_empresa'))
            except Exception as e:
                db.rollback()
                print(f"Erro inesperado: {str(e)}")  # Debug
                flash(f'Erro inesperado: {str(e)}', 'error')
                return redirect(url_for('user_page_bp.cadastrar_empresa'))
            finally:
                cursor.close()
                db.close()
                print("Conexão com banco fechada")  # Debug

        except Exception as e:
            print(f"Erro geral: {str(e)}")  # Debug
            flash(f'Erro no processamento: {str(e)}', 'error')
            return redirect(url_for('user_page_bp.cadastrar_empresa'))

    # Se for GET, mostrar formulário
    opcoes = {
        'centros_trabalho': ['BR45', 'BR20', 'BR31'],
        'segmentos': ['Predial', 'Industrial'],
        'tipos_empresa': ['Contratante', 'Prestadora de Serviço', 'Fornecedora']
    }
    return render_template('cadastrar_empresa.html', opcoes=opcoes)


@user_page_bp.route('/empresa')
def empresa():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']

    # Primeiro verifica se o usuário tem empresa vinculada
    usuario_possui_empresa = False
    db1 = get_db_connection()
    cursor1 = db1.cursor()
    try:
        cursor1.execute("SELECT empresa_id FROM dados_usuario WHERE user_id = %s AND empresa_id IS NOT NULL",
                        (user_id,))
        usuario_possui_empresa = cursor1.fetchone() is not None
        cursor1.fetchall()  # Consome todos os resultados restantes
    except Exception as e:
        print(f"Erro ao verificar empresa vinculada: {str(e)}")
    finally:
        cursor1.close()
        db1.close()

    # Depois verifica se o usuário é criador de alguma empresa
    usuario_eh_criador = False
    db2 = get_db_connection()
    cursor2 = db2.cursor()
    try:
        cursor2.execute("SELECT 1 FROM empresas WHERE criado_por = %s", (user_id,))
        usuario_eh_criador = cursor2.fetchone() is not None
        cursor2.fetchall()  # Consome todos os resultados restantes
    except Exception as e:
        print(f"Erro ao verificar criador de empresa: {str(e)}")
    finally:
        cursor2.close()
        db2.close()

    return render_template('empresa.html',
                           usuario_possui_empresa=usuario_possui_empresa,
                           usuario_eh_criador=usuario_eh_criador)


@user_page_bp.route('/gerenciar_empresa')
def gerenciar_empresa():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Consulta principal das empresas
        cursor.execute("""
            SELECT 
                e.id, e.nome_empresa, e.razao_social, e.cnpj, 
                e.centro_trabalho, e.segmento, e.email_coorporativo,
                e.contato, e.tipo_empresa, e.criado_por,
                u.nome as criador_nome, u.email as criador_email,
                e.responsavel_tecnico, e.responsavel_legal
            FROM empresas e
            JOIN cadastro_usuario u ON e.criado_por = u.id
            WHERE e.criado_por = %s
        """, (user_id,))
        empresas = cursor.fetchall()

        if not empresas:
            flash('Você não criou nenhuma empresa ainda', 'info')
            return redirect(url_for('user_page_bp.empresa'))

        # Busca usuários vinculados para cada empresa
        for empresa in empresas:
            cursor.execute("""
                SELECT 
                    cu.id,
                    cu.nome,
                    cu.email,
                    eu.vinculo,
                    du.treinamentos  # Adicionando esta linha
                FROM empresa_usuarios eu
                JOIN cadastro_usuario cu ON eu.usuario_id = cu.id
                LEFT JOIN dados_usuario du ON cu.id = du.user_id  # LEFT JOIN para pegar os treinamentos
                WHERE eu.empresa_id = %s AND eu.usuario_id IS NOT NULL
            """, (empresa['id'],))
            empresa['usuarios'] = cursor.fetchall()

        opcoes = {
            'centros_trabalho': ['BR45', 'BR20', 'BR31'],
            'treinamentos': ['NR10', 'NR12', 'NR13', 'NR20', 'NR33', 'NR34', 'NR35', 'NR36']
        }

        return render_template('gerenciar_empresa.html',
                               empresas=empresas,
                               segmentos=['Predial', 'Industrial'],
                               tipos_empresa=['Contratante', 'Prestadora de Serviço', 'Fornecedora'],
                               opcoes=opcoes)
    except Exception as e:
        print(f"Erro em gerenciar_empresa: {str(e)}")
        flash('Erro ao carregar informações das empresas', 'error')
        return redirect(url_for('user_page_bp.empresa'))
    finally:
        cursor.close()
        db.close()

# Rota para atualizar empresa
@user_page_bp.route('/atualizar_empresa', methods=['POST'])
def atualizar_empresa():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']
    empresa_id = request.form['empresa_id']

    # Processar responsáveis técnicos (pode ser múltiplos)
    tecnicos = request.form.getlist('responsavel_tecnico')
    tecnicos = [t.strip() for t in tecnicos if t.strip()]
    responsavel_tecnico = ','.join(tecnicos) if tecnicos else None

    # Processar responsáveis legais (pode ser múltiplos)
    legais = request.form.getlist('responsavel_legal')
    legais = [l.strip() for l in legais if l.strip()]
    responsavel_legal = ','.join(legais) if legais else None

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Verifica se o usuário é o criador
        cursor.execute("SELECT criado_por FROM empresas WHERE id = %s", (empresa_id,))
        if cursor.fetchone()[0] != user_id:
            flash('Você não tem permissão para editar esta empresa', 'error')
            return redirect(url_for('user_page_bp.gerenciar_empresa'))

        # Atualiza os dados
        cursor.execute("""
            UPDATE empresas SET
                nome_empresa = %s,
                razao_social = %s,
                cnpj = %s,
                centro_trabalho = %s,  # Adicione esta linha
                segmento = %s,
                tipo_empresa = %s,
                email_coorporativo = %s,
                contato = %s,
                responsavel_tecnico = %s,
                responsavel_legal = %s
            WHERE id = %s
        """, (
            request.form['nome_empresa'],
            request.form['razao_social'],
            request.form['cnpj'],
            request.form['centro_trabalho'],  # Adicione esta linha
            request.form['segmento'],
            request.form['tipo_empresa'],
            request.form['email_coorporativo'],
            request.form.get('contato', ''),
            responsavel_tecnico,
            responsavel_legal,
            empresa_id
        ))

        db.commit()
        flash('Empresa atualizada com sucesso!', 'success')
        return redirect(url_for('user_page_bp.gerenciar_empresa'))
    except Exception as e:
        db.rollback()
        print(f"Erro ao atualizar empresa: {str(e)}")
        flash(f'Erro ao atualizar empresa: {str(e)}', 'error')
        return redirect(url_for('user_page_bp.gerenciar_empresa'))
    finally:
        cursor.close()
        db.close()


# API para listar usuários da empresa
@user_page_bp.route('/api/usuarios_empresa/<int:empresa_id>')
def api_usuarios_empresa(empresa_id):
    if not verify_session():
        return jsonify({'error': 'Não autorizado'}), 401

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Busca usuários vinculados à empresa
        cursor.execute("""
            SELECT 
                eu.id, 
                COALESCE(eu.nome, u.nome) as nome,
                COALESCE(eu.email, u.email) as email,
                eu.vinculo
            FROM empresa_usuarios eu
            LEFT JOIN cadastro_usuario u ON eu.usuario_id = u.id
            WHERE eu.empresa_id = %s
        """, (empresa_id,))

        usuarios = cursor.fetchall()
        return jsonify({'usuarios': usuarios})
    except Exception as e:
        print(f"Erro ao buscar usuários da empresa: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        db.close()


@user_page_bp.route('/atualizar_vinculo_simples/<int:empresa_id>/<int:usuario_id>', methods=['POST'])
def atualizar_vinculo_simples(empresa_id, usuario_id):
    if not verify_session():
        return jsonify({'success': False, 'message': 'Não autorizado'}), 401

    data = request.get_json()
    vinculo = data.get('vinculo')

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Atualiza apenas na tabela empresa_usuarios
        cursor.execute("""
            UPDATE empresa_usuarios 
            SET vinculo = %s
            WHERE usuario_id = %s AND empresa_id = %s
        """, (vinculo, usuario_id, empresa_id))

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        db.close()

@user_page_bp.route('/salvar_treinamentos/<int:empresa_id>/<int:usuario_id>', methods=['POST'])
def salvar_treinamentos(empresa_id, usuario_id):
    if not verify_session():
        return jsonify({'success': False, 'message': 'Não autorizado'}), 401

    data = request.get_json()
    treinamentos = data.get('treinamentos', '')

    db = get_db_connection()
    cursor = db.cursor()
    try:
        # Atualiza os treinamentos na tabela dados_usuario
        cursor.execute("""
            UPDATE dados_usuario 
            SET treinamentos = %s
            WHERE user_id = %s
        """, (treinamentos, usuario_id))

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        db.close()

@user_page_bp.route('/adicionar_treinamento/<int:empresa_id>/<int:usuario_id>', methods=['POST'])
def adicionar_treinamento(empresa_id, usuario_id):
    if not verify_session():
        return jsonify({'success': False, 'message': 'Não autorizado'}), 401

    data = request.get_json()
    novo_treinamento = data.get('treinamento', '')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Pega os treinamentos atuais
        cursor.execute("SELECT treinamentos FROM dados_usuario WHERE user_id = %s", (usuario_id,))
        result = cursor.fetchone()
        treinamentos = result['treinamentos'] if result and result['treinamentos'] else ""

        # Adiciona o novo treinamento
        treinamentos_list = treinamentos.split(',') if treinamentos else []
        if novo_treinamento not in treinamentos_list:
            treinamentos_list.append(novo_treinamento)
            novos_treinamentos = ','.join(treinamentos_list)

            # Atualiza no banco
            cursor.execute("""
                UPDATE dados_usuario 
                SET treinamentos = %s
                WHERE user_id = %s
            """, (novos_treinamentos, usuario_id))
            db.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        db.close()

@user_page_bp.route('/remover_treinamento/<int:empresa_id>/<int:usuario_id>', methods=['POST'])
def remover_treinamento(empresa_id, usuario_id):
    if not verify_session():
        return jsonify({'success': False, 'message': 'Não autorizado'}), 401

    data = request.get_json()
    treinamento_remover = data.get('treinamento', '')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Pega os treinamentos atuais
        cursor.execute("SELECT treinamentos FROM dados_usuario WHERE user_id = %s", (usuario_id,))
        result = cursor.fetchone()
        if not result or not result['treinamentos']:
            return jsonify({'success': False, 'message': 'Nenhum treinamento encontrado'})

        # Remove o treinamento
        treinamentos_list = result['treinamentos'].split(',')
        if treinamento_remover in treinamentos_list:
            treinamentos_list.remove(treinamento_remover)
            novos_treinamentos = ','.join(treinamentos_list)

            # Atualiza no banco
            cursor.execute("""
                UPDATE dados_usuario 
                SET treinamentos = %s
                WHERE user_id = %s
            """, (novos_treinamentos, usuario_id))
            db.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        db.close()


import os
from werkzeug.utils import secure_filename

# Configurações
CERTIFICADOS_FOLDER = os.path.join('static', 'certificados')
ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@user_page_bp.route('/user_treinamentos', methods=['GET', 'POST'])
def user_treinamentos():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Obter dados do usuário
        cursor.execute("""
            SELECT du.treinamentos, du.empresa_id, du.certificados,
                   e.nome_empresa, cu.nome as user_name
            FROM dados_usuario du
            JOIN cadastro_usuario cu ON du.user_id = cu.id
            LEFT JOIN empresas e ON du.empresa_id = e.id
            WHERE du.user_id = %s
        """, (user_id,))
        user_data = cursor.fetchone()

        if not user_data:
            flash('Dados do usuário não encontrados', 'error')
            return redirect(url_for('user_page_bp.user_page'))

        # Processar certificados (JSON ou dicionário vazio)
        certificados = json.loads(user_data['certificados']) if user_data['certificados'] else {}

        # Processar treinamentos
        treinamentos = []
        if user_data.get('treinamentos'):
            for treinamento in user_data['treinamentos'].split(','):
                if treinamento.strip():
                    # Verifica se tem certificado registrado
                    has_certificado = treinamento.strip() in certificados
                    arquivo = None

                    if has_certificado:
                        arquivo = certificados[treinamento.strip()]
                    else:
                        # Verifica no sistema de arquivos (backward compatibility)
                        old_file = buscar_certificado(user_data['empresa_id'], user_id, treinamento.strip())
                        if old_file:
                            arquivo = old_file.replace('\\', '/')
                            # Atualiza no banco
                            certificados[treinamento.strip()] = arquivo

                    treinamentos.append({
                        'nome': treinamento.strip(),
                        'arquivo': arquivo
                    })

        # Atualizar certificados no banco se necessário
        if any(t['arquivo'] for t in treinamentos) and not user_data['certificados']:
            cursor.execute("""
                UPDATE dados_usuario 
                SET certificados = %s 
                WHERE user_id = %s
            """, (json.dumps(certificados), user_id))
            db.commit()

        # Processar POST (upload)
        if request.method == 'POST':
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                treinamento_nome = request.form.get('treinamento_nome')
                file = request.files.get('certificado')

                if file and allowed_file(file.filename):
                    filename = secure_filename(f"{treinamento_nome}.pdf")
                    save_path = criar_caminho_certificado(user_data['empresa_id'], user_id, filename)
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    file.save(save_path)

                    # Atualiza no banco
                    certificados[
                        treinamento_nome] = f"certificados/empresa_{user_data['empresa_id']}/usuario_{user_id}/{filename}"
                    cursor.execute("""
                        UPDATE dados_usuario 
                        SET certificados = %s 
                        WHERE user_id = %s
                    """, (json.dumps(certificados), user_id))
                    db.commit()

                    return jsonify({
                        'success': True,
                        'file_url': url_for('static', filename=certificados[treinamento_nome])
                    })

            # Comportamento original para não-AJAX
            if 'remover_certificado' in request.form:
                return remover_certificado()

        return render_template('user_treinamentos.html',
                               treinamentos=treinamentos,
                               empresa_nome=user_data.get('nome_empresa', 'Não vinculado'),
                               user_nome=user_data.get('user_name', 'Usuário'))

    except Exception as e:
        print(f"Erro em user_treinamentos: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        flash('Erro ao carregar treinamentos', 'error')
        return redirect(url_for('user_page_bp.user_page'))
    finally:
        cursor.close()
        db.close()


def criar_caminho_certificado(empresa_id, user_id, filename):
    return os.path.join(CERTIFICADOS_FOLDER, f"empresa_{empresa_id}", f"usuario_{user_id}", filename)


def buscar_certificado(empresa_id, user_id, treinamento_nome):
    caminho = os.path.join(CERTIFICADOS_FOLDER, f"empresa_{empresa_id}", f"usuario_{user_id}",
                           f"{treinamento_nome}.pdf")
    return caminho if os.path.exists(caminho) else None


from flask import send_from_directory  # Adicione esta importação no início do arquivo

@user_page_bp.route('/download_certificado/<path:filename>')
def download_certificado(filename):
    if not verify_session():
        return redirect(url_for('login.login'))

    # Segurança: verificar se o usuário tem permissão para acessar este arquivo
    user_id = session['user_id']
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT empresa_id FROM dados_usuario WHERE user_id = %s", (user_id,))
        empresa_id = cursor.fetchone()['empresa_id']

        # Construa o caminho completo do arquivo
        file_dir = os.path.join(
            current_app.root_path,  # Adiciona o caminho raiz do aplicativo
            CERTIFICADOS_FOLDER,
            f"empresa_{empresa_id}",
            f"usuario_{user_id}"
        )
        file_path = os.path.join(file_dir, filename)

        # Verificação adicional de segurança
        if not filename.endswith('.pdf') or '../' in filename:
            flash('Tipo de arquivo inválido', 'error')
            return redirect(url_for('user_page_bp.user_treinamentos'))

        if os.path.exists(file_path):
            return send_from_directory(
                directory=file_dir,
                path=filename,
                as_attachment=True
            )
        else:
            flash('Arquivo não encontrado', 'error')
            return redirect(url_for('user_page_bp.user_treinamentos'))
    except Exception as e:
        print(f"Erro ao baixar certificado: {str(e)}")
        flash('Erro ao baixar certificado', 'error')
        return redirect(url_for('user_page_bp.user_treinamentos'))
    finally:
        cursor.close()
        db.close()


@user_page_bp.route('/remover_certificado', methods=['POST'])
def remover_certificado():
    if not verify_session():
        return redirect(url_for('login.login'))

    user_id = session['user_id']
    treinamento_nome = request.form.get('treinamento_nome')

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Obter dados atuais
        cursor.execute("SELECT certificados FROM dados_usuario WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        certificados = json.loads(result['certificados']) if result and result['certificados'] else {}

        # Remover certificado
        if treinamento_nome in certificados:
            file_path = os.path.join('static', certificados[treinamento_nome])
            if os.path.exists(file_path):
                os.remove(file_path)

            del certificados[treinamento_nome]

            # Atualizar banco
            cursor.execute("""
                UPDATE dados_usuario 
                SET certificados = %s 
                WHERE user_id = %s
            """, (json.dumps(certificados), user_id))
            db.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True})
        return redirect(url_for('user_page_bp.user_treinamentos'))

    except Exception as e:
        print(f"Erro ao remover certificado: {str(e)}")
        db.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        flash('Erro ao remover certificado', 'error')
        return redirect(url_for('user_page_bp.user_treinamentos'))
    finally:
        cursor.close()
        db.close()

@user_page_bp.route('/documentacoes')
def documentacoes():
    """Documentações"""
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('documentacoes.html')

@user_page_bp.route('/documentacao/ativos')
def documentacao_ativos():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('documentacao_ativos.html')

# Rotas para as subpáginas (todas levam para a mesma página de construção)
@user_page_bp.route('/documentacao/manuais-operacao')
def manuais_operacao():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/especificacoes-tecnicas')
def especificacoes_tecnicas():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/procedimentos-inicializacao')
def procedimentos_inicializacao():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/configuracao-sistemas')
def configuracao_sistemas():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/historico-manutencao')
def historico_manutencao():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/procedimentos-operacionais')
def procedimentos_operacionais():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/medidas-seguranca')
def medidas_seguranca():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/instrucoes-tecnicas')
def instrucoes_tecnicas():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacao/padroes-conformidade')
def padroes_conformidade():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos')
def documentacao_procedimentos():
    """Página principal de Documentação de Procedimentos (com o menu)"""
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('documentacao_procedimentos.html')

# Rotas para as subpáginas (todas levam para a página de construção)
@user_page_bp.route('/documentacoes/procedimentos/instrucoes-trabalho')
def instrucoes_trabalho():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/guias-execucao')
def guias_execucao():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/assinaturas-digitais')
def assinaturas_digitais():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/normas-seguranca')
def normas_seguranca():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/diretrizes-regulamentacoes')
def diretrizes_regulamentacoes():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/epi-epc')
def documentacoes_epi_epc():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/procedimentos/procedimentos-emergencia')
def procedimentos_emergencia():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal')
def documentacao_legal():
    """Página principal de Documentação Legal (com o menu)"""
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('documentacao_legal.html')

# Rotas para as subpáginas (todas levam para a página de construção)
@user_page_bp.route('/documentacoes/legal/certificados-conformidade')
def certificados_conformidade():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/certificacao-equipamentos')
def certificacao_equipamentos():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/licencas-permissoes')
def licencas_permissoes():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/historico-renovacao')
def historico_renovacao():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/relatorios-auditoria')
def relatorios_auditoria():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/validacao-conformidade')
def validacao_conformidade():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/analise-riscos')
def analise_riscos():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/gestao-nao-conformidade')
def gestao_nao_conformidade():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')

@user_page_bp.route('/documentacoes/legal/assinatura-digital')
def assinatura_digital():
    if not verify_session():
        return redirect(url_for('login'))
    return render_template('em_construcao.html')