from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Welcome to Vinjak</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #ff9a9e, #fad0c4);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            text-align: center;
            font-family: 'Arial', sans-serif;
        }
        .card {
            padding: 20px;
            border-radius: 15px;
            background: rgba(255, 255, 255, 0.8);
            box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.2);
        }
        .handle {
            font-size: 24px;
            font-weight: bold;
            color: #ff4d4d;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Welcome to Vinjak</h1>
        <p>Your Telegram Handle:</p>
        <p class="handle">tg~@vinjak</p>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

if __name__ == "__main__":
    app.run(debug=True)
