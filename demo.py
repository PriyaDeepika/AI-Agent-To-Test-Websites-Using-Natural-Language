"""Local demo sites for *regression testing only* (login, dashboard, shop with 3 option layouts, overlay,
CAPTCHA wall, delayed results). They are served by the same Flask app under /demo/*."""
from flask import Blueprint, render_template_string, request, session, redirect, url_for, abort

demo = Blueprint("demo", __name__, url_prefix="/demo")

PRODUCTS = [
    (1, "Nike Air Zoom Pegasus Women's Running Shoes", 89.99, "women", "nike"),
    (2, "Nike Women's Revolution 6 Road Running Shoes", 64.99, "women", "nike"),
    (3, "Nike Men's Downshifter 12 Running Shoes", 59.99, "men", "nike"),
    (4, "Adidas Women's Ultraboost Light Shoes", 129.99, "women", "adidas"),
    (5, "Puma Women's Softride Enzo Sneakers", 44.99, "women", "puma"),
    (6, "Nike Women's Court Vision Low Sneakers", 74.99, "women", "nike"),
    (7, "Linux Administration Handbook (Paperback)", 39.50, "books", "book"),
]
SIZES = [5, 6, 7, 8, 9, 10, 11]
OUT_OF_STOCK = {(1, 9)}

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{ title }}</title>
<style>body{font-family:system-ui,sans-serif;margin:0}header{display:flex;gap:1rem;align-items:center;padding:.8rem 1.2rem;background:#f1f3f5}
main{padding:1.2rem;max-width:960px;margin:auto}.grid{list-style:none;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}
.product-card{border:1px solid #ddd;padding:.8rem}.price{font-weight:700}.size-btn{margin:.2rem;padding:.4rem .8rem}.size-btn[aria-pressed=true]{background:#222;color:#fff}
#cookie-banner{position:fixed;inset:auto 0 0 0;background:#222;color:#fff;padding:1rem;z-index:99;display:flex;gap:1rem}
#cookie-banner.full{inset:0;align-items:center;justify-content:center;background:rgba(0,0,0,.8)}.err{color:#b00020}[hidden]{display:none!important}
ul[role=listbox]{list-style:none;border:1px solid #bbb;padding:0;width:140px}ul[role=listbox] li{padding:.3rem .6rem;cursor:pointer}</style></head><body>
<header><a href="{{ url_for('demo.shop') }}"><strong>DemoShop</strong></a>
<form action="{{ url_for('demo.shop') }}" method="get" role="search"><input type="search" name="q" placeholder="Search products" aria-label="Search" value="{{ q or '' }}">
<input type="hidden" name="banner" value="{{ banner }}"><input type="hidden" name="layout" value="{{ layout }}"><button type="submit">Search</button></form>
<a href="{{ url_for('demo.cart') }}" aria-label="Shopping cart" id="cart-link">Cart <span id="cart-count">{{ cart_n }}</span></a></header>
{% if banner %}<div id="cookie-banner" class="{{ 'full' if banner == 'full' else '' }}" role="dialog" aria-label="Cookie consent"><span>We use cookies.</span>
<button onclick="document.getElementById('cookie-banner').remove()">Accept all</button></div>{% endif %}
<main>{{ body|safe }}</main></body></html>"""


def render(title, body_tpl, **ctx):
    body = render_template_string(body_tpl, **ctx)
    cart = session.get("cart", [])
    return render_template_string(BASE, title=title, body=body, cart_n=len(cart), q=ctx.get("q"),
                                  banner=request.args.get("banner", ""), layout=request.args.get("layout", ""))


def _keep():
    return {k: request.args[k] for k in ("banner", "layout", "delay") if request.args.get(k)}


@demo.route("/shop")
def shop():
    q = request.args.get("q", "").strip().lower()
    hits = [p for p in PRODUCTS if not q or all(t.rstrip("s") in p[1].lower() or t in p[1].lower() for t in q.replace("'", "").split() if t not in ("for", "the", "a"))]
    delay = request.args.get("delay")
    tpl = """<h1>{% if q %}Results for “{{ q }}”{% else %}All products{% endif %}</h1>
    {% if delay %}<p id="loading">Loading results…</p><ul class="grid" id="results"></ul>
    <script>setTimeout(()=>{document.getElementById('loading').remove();document.getElementById('results').innerHTML={{ html|tojson }};}, {{ delay|int }});</script>
    {% else %}<ul class="grid" id="results">{{ html|safe }}</ul>{% endif %}
    {% if not hits %}<p>No results found.</p>{% endif %}"""
    html = "".join(f'<li class="product-card"><a href="{url_for("demo.item", pid=p[0], **_keep())}">{p[1]}</a><div class="price">${p[2]:.2f}</div></li>' for p in hits)
    return render("DemoShop", tpl, q=q, html=html, hits=hits, delay=delay)


@demo.route("/shop/item/<int:pid>")
def item(pid, error=None):
    p = next((x for x in PRODUCTS if x[0] == pid), None) or abort(404)
    layout = request.args.get("layout", "select")
    tpl = """<h1>{{ p[1] }}</h1><p class="price">${{ '%.2f'|format(p[2]) }}</p>
    {% if error %}<p class="err" role="alert">{{ error }}</p>{% endif %}
    <form method="post" action="{{ url_for('demo.cart_add', **keep) }}"><input type="hidden" name="pid" value="{{ p[0] }}">
    {% if p[3] != 'books' %}
      {% if layout == 'swatch' %}<fieldset><legend>Size</legend>{% for s in sizes %}<button type="button" class="size-btn" aria-pressed="false" {{ 'disabled' if (p[0], s) in oos }}
        onclick="document.querySelectorAll('.size-btn').forEach(b=>b.setAttribute('aria-pressed','false'));this.setAttribute('aria-pressed','true');document.getElementById('size-input').value='{{ s }}'">{{ s }}</button>{% endfor %}</fieldset>
        <input type="hidden" name="size" id="size-input" value="">
      {% elif layout == 'dropdown' %}<label id="size-label">Size</label><button type="button" role="combobox" aria-haspopup="listbox" aria-label="Size" id="size-trigger"
        onclick="document.getElementById('size-list').hidden=!document.getElementById('size-list').hidden">Select</button>
        <ul role="listbox" id="size-list" hidden>{% for s in sizes %}<li role="option" tabindex="0" onclick="document.getElementById('size-input').value='{{ s }}';document.getElementById('size-trigger').textContent='{{ s }}';document.getElementById('size-list').hidden=true">{{ s }}</li>{% endfor %}</ul>
        <input type="hidden" name="size" id="size-input" value="">
      {% else %}<label for="size">Size</label> <select id="size" name="size"><option value="">Select size</option>
        {% for s in sizes %}<option value="{{ s }}" {{ 'disabled' if (p[0], s) in oos }}>US {{ s }}{{ ' (sold out)' if (p[0], s) in oos }}</option>{% endfor %}</select>{% endif %}
    {% endif %}
    <p><button type="submit">Add to cart</button> <button type="submit" formaction="{{ url_for('demo.checkout') }}">Buy it now</button></p></form>"""
    return render(p[1], tpl, p=p, sizes=SIZES, oos=OUT_OF_STOCK, layout=layout, error=error, keep=_keep())


@demo.route("/cart/add", methods=["POST"])
def cart_add():
    pid = int(request.form.get("pid", 0))
    size = request.form.get("size", "")
    p = next((x for x in PRODUCTS if x[0] == pid), None) or abort(404)
    if p[3] != "books" and not size:
        return item(pid, error="Please select a size before adding to cart.")
    session.setdefault("cart", [])
    session["cart"] = session["cart"] + [{"pid": pid, "title": p[1], "price": p[2], "size": size}]
    return redirect(url_for("demo.cart", added=1, **_keep()))


@demo.route("/cart")
def cart():
    items = session.get("cart", [])
    tpl = """<h1>Shopping cart</h1>{% if request.args.get('added') %}<p role="status">Item added to your cart.</p>{% endif %}
    {% if not items %}<p>Your cart is empty.</p>{% else %}<ul>{% for i in items %}<li class="cart-line"><a href="{{ url_for('demo.item', pid=i.pid) }}">{{ i.title }}</a>
    — Size {{ i.size or 'n/a' }} — ${{ '%.2f'|format(i.price) }}</li>{% endfor %}</ul><button>Proceed to checkout</button>{% endif %}"""
    return render("Cart", tpl, items=items)


@demo.route("/checkout", methods=["GET", "POST"])
def checkout():
    session["checkout_reached"] = True   # tests assert the agent never gets here without confirmation
    return render("Checkout", "<h1>Checkout</h1><p id='checkout-page'>Payment details required. Place order?</p>")


@demo.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        if request.form.get("username") == "demo" and request.form.get("password") == "test1234":
            session["user"] = "demo"
            return redirect(url_for("demo.dashboard"))
        err = "Invalid username or password."
    tpl = """<h1>Sign in</h1>{% if err %}<p class="err" role="alert">{{ err }}</p>{% endif %}
    <form method="post"><label>Username <input type="text" name="username" autocomplete="username"></label><br>
    <label>Password <input type="password" name="password"></label><br><button type="submit">Sign in</button></form>"""
    return render("Sign in", tpl, err=err)


@demo.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect(url_for("demo.login"))
    return render("Dashboard", "<h1>Dashboard</h1><p>Welcome back, {{ u }}!</p><ul><li>Open orders: 2</li><li>Account balance: $120.00</li></ul>", u=session["user"])


@demo.route("/captcha")
def captcha():
    return render("Security check", "<h1>Security check</h1><p>Please verify you are human to continue. CAPTCHA required.</p><div style='width:300px;height:70px;border:1px solid #888'>[ CAPTCHA ]</div>")


@demo.route("/broken")
def broken():
    abort(500)
