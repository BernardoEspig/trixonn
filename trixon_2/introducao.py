from flask import jsonify, current_app, Blueprint, Flask, render_template, request, redirect, url_for, flash, session
import uuid
from datetime import datetime, timedelta
from psycopg2.extras import DictCursor

introducao_bp = Blueprint('introducao_bp', __name__)

@introducao_bp.route('/introducao')
def introducao():
    return render_template('introducao.html')

@introducao_bp.route('/')
def a():
    return render_template('animacao.html')


