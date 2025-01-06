from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
import bcrypt
import re
from decimal import Decimal




app = Flask(__name__)

# MySQL configurations
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'Flask'
app.config['MYSQL_PASSWORD'] = 'f1@skApp'
app.config['MYSQL_DB'] = 'market_tracker'

mysql = MySQL(app)

app.secret_key = 'your_secret_key'

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        account = cursor.fetchone()
        cursor.close()

        if account:
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            session['role'] = account['role']
            return redirect(url_for('dashboard'))
        else:
            return 'Invalid login credentials!'
    return render_template('login.html')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = 'user'
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)', (username, email, password, role))
        mysql.connection.commit()
        cursor.close()
        
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT product, state, market_name, price FROM prices WHERE status = "approved"')
    prices = cursor.fetchall()
    cursor.close()
    return render_template('dashboard.html', prices=prices)



@app.route('/comparison', methods=['GET', 'POST'])
def comparison():
    if request.method == 'POST':
        product = request.form['product']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT product, state, market_name, price FROM prices WHERE product = %s AND status = "approved"', (product,))
        comparison_data = cursor.fetchall()
        cursor.close()
        
        return render_template('comparison.html', comparison_data=comparison_data)
    return render_template('comparison.html')



@app.route('/trends', methods=['GET', 'POST'])
def trends():
    trends_data = []
    if request.method == 'POST':
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        product = request.form['product']
        state = request.form['state']

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        if state == 'Nigeria':
            query = '''
                SELECT date, AVG(price) as mean_price
                FROM prices
                WHERE product = %s AND date BETWEEN %s AND %s AND status = "approved"
                GROUP BY date ORDER BY date
            '''
            params = [product, start_date, end_date]
        else:
            query = '''
                SELECT date, AVG(price) as mean_price
                FROM prices
                WHERE product = %s AND state = %s AND date BETWEEN %s AND %s AND status = "approved"
                GROUP BY date ORDER BY date
            '''
            params = [product, state, start_date, end_date]

        cursor.execute(query, tuple(params))
        trends_data = cursor.fetchall()
        cursor.close()

        # Convert datetime and decimal to string for JSON serialization
        trends_data = [
            {'date': record['date'].strftime('%Y-%m-%d'), 'mean_price': float(record['mean_price'])}
            for record in trends_data
        ]
        print(jsonify(trends_data))

        return jsonify(trends_data)

    states = ['Nigeria'] + get_states()
    products = get_products()
    return render_template('trends.html', trends_data=trends_data, states=states, products=products)


def get_states():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT DISTINCT state FROM prices WHERE status = 'approved'")
    states = cursor.fetchall()
    cursor.close()
    return [state['state'] for state in states]

def get_products():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT DISTINCT product FROM prices WHERE status = 'approved'")
    products = cursor.fetchall()
    cursor.close()
    return [product['product'] for product in products]



@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        product = request.form['product']
        price = request.form['price']
        state = request.form['state']
        market_name = request.form['market_name']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('INSERT INTO prices (product, price, state, market_name, user_id) VALUES (%s, %s, %s, %s, %s)', (product, price, state, market_name, session['id']))
        mysql.connection.commit()
        cursor.close()
        
        return redirect(url_for('dashboard'))
    return render_template('submit.html')


@app.route('/notifications', methods=['GET', 'POST'])
def notifications():
    if request.method == 'POST':
        # Handle notifications settings
        return redirect(url_for('dashboard'))
    return render_template('notifications.html')

@app.route('/admin')
def admin():
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    page = request.args.get('page', 1, type=int)
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT COUNT(*) FROM prices WHERE status = "pending"')
    total_submissions = cursor.fetchone()['COUNT(*)']

    per_page = 20
    offset = (page - 1) * per_page

    cursor.execute('SELECT prices.id, prices.product, prices.state, prices.market_name, prices.price, prices.date, users.username FROM prices JOIN users ON prices.user_id = users.id WHERE prices.status = "pending" ORDER BY prices.date DESC LIMIT %s OFFSET %s', (per_page, offset))
    submissions = cursor.fetchall()
    cursor.close()

    return render_template('admin.html', submissions=submissions, total_submissions=total_submissions, page=page, per_page=per_page)

@app.route('/admin/approve/<int:id>', methods=['POST'])
def approve_submission(id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('UPDATE prices SET status = "approved" WHERE id = %s', (id,))
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('admin'))

@app.route('/admin/reject/<int:id>', methods=['POST'])
def reject_submission(id):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('UPDATE prices SET status = "rejected" WHERE id = %s', (id,))
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('admin'))


@app.route('/admin_register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        secret_key = request.form['secret_key']
        if secret_key != 'musamusa':  # replace 'YOUR_SECRET_KEY' with a strong, secure key
            return 'Unauthorized'

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = 'admin'

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)', (username, email, password, role))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('login'))
    return render_template('admin_register.html')



@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
