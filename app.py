from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
import bcrypt
from werkzeug.utils import secure_filename
import re
from decimal import Decimal
import os
import math 


app = Flask(__name__)

#image upload
import os

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
            session['email'] = account['email']  # ✅ Capture user's email in session
            session['role'] = account['role']
            session['is_admin'] = (account['role'].lower() == 'admin')
            return redirect(url_for('dashboard'))
        else:
            return 'Invalid login credentials!'

    return render_template('login.html')

#image universal oic
def get_product_image(product_name):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT image_path FROM products WHERE name = %s", (product_name,))
    result = cursor.fetchone()
    return result[0] if result else None
  

#new image code 
@app.route('/upload_product_image/<product>', methods=['POST'])
def upload_product_image(product):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    if 'image' not in request.files:
        flash('No image uploaded', 'danger')
        return redirect(url_for('admin'))

    file = request.files['image']
    if file.filename == '':
        flash('No image selected', 'danger')
        return redirect(url_for('admin'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        cursor = mysql.connection.cursor()
        # Check if product exists in products table
        cursor.execute("SELECT id FROM products WHERE name = %s", (product,))
        product_row = cursor.fetchone()
        if product_row:
            # Update existing product image
            cursor.execute("UPDATE products SET image_path = %s WHERE name = %s", (filename, product))
        else:
            # Insert new product with image
            cursor.execute("INSERT INTO products (name, image_path) VALUES (%s, %s)", (product, filename))
        mysql.connection.commit()
        cursor.close()
        flash(f'Image uploaded for {product}', 'success')
    else:
        flash('Invalid image file type', 'danger')

    return redirect(url_for('admin'))

@app.route('/change_product_image/<product>', methods=['POST'])
def change_product_image(product):
    if 'loggedin' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    if 'image' not in request.files:
        flash('No file part')
        return redirect(url_for('admin'))

    file = request.files['image']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('admin'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Update product_images table
        cursor = mysql.connection.cursor()
        cursor.execute("REPLACE INTO product_images (product, image_path) VALUES (%s, %s)", (product, filename))
        mysql.connection.commit()
        cursor.close()

        flash('Image updated successfully for product: ' + product)

    return redirect(url_for('admin'))



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = 'user'

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # Check if username or email already exists
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            if existing_user['username'] == username:
                flash('Username already taken. Please choose another.', 'danger')
            elif existing_user['email'] == email:
                flash('Email already registered. Please use another.', 'danger')
            cursor.close()
            return redirect(url_for('register'))

        # If not existing, insert new user
        cursor.execute('INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)',
                       (username, email, password, role))
        mysql.connection.commit()
        cursor.close()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

#notification for messages for the admin
@app.context_processor
def inject_user_and_notifications():
    pending_count = 0
    is_admin = session.get('is_admin', False)

    if session.get('loggedin') and is_admin:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT COUNT(*) AS count FROM prices WHERE status = 'pending'")
        result = cursor.fetchone()
        pending_count = result['count'] if result else 0
        cursor.close()

    return dict(is_admin=is_admin, pending_count=pending_count)



@app.route('/dashboard')
def dashboard():
    PER_PAGE = 20
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * PER_PAGE

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Count total approved prices
    cursor.execute("SELECT COUNT(*) as count FROM prices WHERE status = 'approved'")
    total = cursor.fetchone()['count']

    # Fetch paginated approved prices
    cursor.execute("""
        SELECT prices.id, prices.product, prices.state, prices.market_name, prices.price,
               products.image_path
        FROM prices
        LEFT JOIN products ON prices.product = products.name
        WHERE prices.status = 'approved'
        ORDER BY prices.date DESC
        LIMIT %s OFFSET %s
    """, (PER_PAGE, offset))
    prices = cursor.fetchall()
    cursor.close()

    total_pages = (total + PER_PAGE - 1) // PER_PAGE  # ceil without importing math

    return render_template('dashboard.html', prices=prices, page=page, total_pages=total_pages)



@app.route('/comparison', methods=['GET', 'POST'])
def comparison():
  comparison_data = []
  product = ""
  selected_states = []
  page = request.args.get('page', 1, type=int)
  per_page = 20
  total_pages = 0
  
  all_states = [
      "All States", "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River",
      "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi",
      "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto",
      "Taraba", "Yobe", "Zamfara"
  ]
  
  if request.method == 'POST':
      product = request.form['product']
      selected_states = request.form.getlist('states')
      return redirect(url_for('comparison', product=product, states=','.join(selected_states), page=1))
  
  product = request.args.get('product', '')
  selected_states = request.args.get('states', '').split(',') if request.args.get('states') else []
  
  if product:
      cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
  
      product_keywords = [product.lower()] + [
          word.strip().lower() for word in product.replace('bag of', '').replace('bg of', '').replace('local', '').split()
      ]
  
      where_clauses = ['status = "approved"']
      values = []
  
      if selected_states and "All States" not in selected_states:
        where_clauses.append('state IN %s')
        values.append(tuple(selected_states))



      product_conditions = ' OR '.join(['LOWER(product) LIKE %s' for _ in product_keywords])
      where_clauses.append(f'({product_conditions})')
      values.extend([f"%{kw}%" for kw in product_keywords])
  
      where_sql = ' AND '.join(where_clauses)
  
      count_query = f'SELECT COUNT(*) as count FROM prices WHERE {where_sql}'
      cursor.execute(count_query, tuple(values))
      total_records = cursor.fetchone()['count']
      total_pages = math.ceil(total_records / per_page)
  
      offset = (page - 1) * per_page
      data_query = f'''
          SELECT product, state, market_name, price
          FROM prices
          WHERE {where_sql}
          ORDER BY
              CASE
                  WHEN LOWER(product) = %s THEN 0
                  WHEN LOWER(product) LIKE %s THEN 1
                  ELSE 2
              END,
              id DESC
          LIMIT %s OFFSET %s
      '''
  
      values_with_priority = values + [product.lower(), f"%{product.lower()}%", per_page, offset]
      cursor.execute(data_query, tuple(values_with_priority))
      comparison_data = cursor.fetchall()
      cursor.close()
  
  return render_template(
      'comparison.html',
      comparison_data=comparison_data,
      product=product,
      selected_states=selected_states,
      all_states=all_states,
      page=page,
      total_pages=total_pages
  )



@app.route('/trends', methods=['GET'])
def trends():
    states = get_states()
    products = get_products()
    return render_template('trends.html', states=states, products=products)

@app.route('/get_trends_data', methods=['POST'])
def get_trends_data():
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    product = request.form['product']
    state = request.form['state']

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if state == 'Nigeria':
        query = '''
            SELECT date, AVG(price) as mean_price
            FROM prices
            WHERE product = %s AND date BETWEEN %s AND %s AND status = 'approved'
            GROUP BY date ORDER BY date
        '''
        params = [product, start_date, end_date]
    else:
        query = '''
            SELECT date, AVG(price) as mean_price
            FROM prices
            WHERE product = %s AND state = %s AND date BETWEEN %s AND %s AND status = 'approved'
            GROUP BY date ORDER BY date
        '''
        params = [product, state, start_date, end_date]

    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()

    trends_data = [
        {
            'date': record['date'].strftime('%Y-%m-%d'),
            'mean_price': float(record['mean_price']) if record['mean_price'] is not None else 0.0
        }
        for record in results
    ]

    return jsonify(trends_data)


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
        raw_price = request.form['price']
        state = request.form['state']
        market_name = request.form['market_name']

        # Clean and convert price
        clean_price = raw_price.replace('₦', '').replace(',', '').strip()
        try:
            price = float(clean_price)
        except ValueError:
            flash('Invalid price format. Please enter a valid number.')
            return redirect(url_for('submit'))

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute(
            'INSERT INTO prices (product, price, state, market_name, user_id) VALUES (%s, %s, %s, %s, %s)',
            (product, price, state, market_name, session.get('id', 0))
        )
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

    # Total number of pending submissions
    cursor.execute('SELECT COUNT(*) FROM prices WHERE status = "pending"')
    total_submissions = cursor.fetchone()['COUNT(*)']

    per_page = 20
    offset = (page - 1) * per_page

    # Join prices with users and LEFT JOIN products to get product image
    cursor.execute('''
        SELECT prices.id, prices.product, prices.state, prices.market_name, prices.price, prices.date, 
               users.username, products.image_path 
        FROM prices 
        JOIN users ON prices.user_id = users.id 
        LEFT JOIN products ON prices.product = products.name
        WHERE prices.status = "pending" 
        ORDER BY prices.date DESC 
        LIMIT %s OFFSET %s
    ''', (per_page, offset))

    submissions = cursor.fetchall()
    cursor.close()

    return render_template('admin.html', submissions=submissions, total_submissions=total_submissions, page=page, per_page=per_page)

@app.route('/approve/<int:id>', methods=['POST'])
def approve_submission(id):
    cursor = mysql.connection.cursor()

    # Get the submission
    cursor.execute("SELECT product FROM prices WHERE id = %s", (id,))
    product_row = cursor.fetchone()
    if not product_row:
        flash('Submission not found.', 'danger')
        return redirect(url_for('admin'))

    product_name = product_row[0]

    # Check if an image was uploaded
    if 'image' in request.files:
        image = request.files['image']
        if image.filename != '':
            filename = secure_filename(image.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(filepath)

            # Insert or update the product image
            cursor.execute("SELECT id FROM products WHERE name = %s", (product_name,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE products SET image_path = %s WHERE name = %s", (filename, product_name))
            else:
                cursor.execute("INSERT INTO products (name, image_path) VALUES (%s, %s)", (product_name, filename))
    
    # Approve the submission
    cursor.execute("UPDATE prices SET status = 'approved' WHERE id = %s", (id,))
    mysql.connection.commit()
    flash('Submission approved!', 'success')
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


@app.route("/quote_request", methods=["GET", "POST"])
def quote_request():
    if not session.get("loggedin"):
        return redirect("/login")

    user_email = session.get("email")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == "POST":
        product_name = request.form["product_name"]
        category = request.form.get("category")
        description = request.form.get("description")
        phone = request.form.get("phone")
        image = request.files.get("image")

        image_path = None
        if image and image.filename != "":
            filename = secure_filename(image.filename)
            image.save(os.path.join("static/uploads", filename))
            image_path = filename

        cursor.execute("""
            INSERT INTO quote_requests (product_name, category, description, email, phone, image_path)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (product_name, category, description, user_email, phone, image_path))
        mysql.connection.commit()
        flash("Your quote request has been submitted!", "success")
        return redirect("/quote_request")

    # Fetch existing quote requests for the logged-in user
    cursor.execute("SELECT * FROM quote_requests WHERE email = %s ORDER BY submitted_at DESC", (user_email,))
    my_requests = cursor.fetchall()

    return render_template("quote_request.html", my_requests=my_requests)


@app.route("/admin/quote_requests", methods=["GET", "POST"])
def admin_quote_requests():
    if not session.get("loggedin") or not session.get("is_admin"):
        return redirect("/login")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == "POST":
        req_id = request.form.get("request_id")
        response = request.form.get("response")
        price = request.form.get("price")
        location = request.form.get("availability_location")
        supplier_contact = request.form.get("supplier_contact")

        cursor.execute("""
            UPDATE quote_requests
            SET response=%s, price=%s, availability_location=%s, supplier_contact=%s
            WHERE id=%s
        """, (response, price, location, supplier_contact, req_id))
        mysql.connection.commit()
        flash("Response sent successfully.", "success")
        return redirect("/admin/quote_requests")

    cursor.execute("SELECT * FROM quote_requests ORDER BY submitted_at DESC")
    requests = cursor.fetchall()

    return render_template("admin_quote_requests.html", requests=requests)




@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))



if __name__ == '__main__':
    app.run(debug=True)
