from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import User, Device

app=create_app({'START_MONITORING': False})
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first(): db.session.add(User(username='admin',password_hash=generate_password_hash('admin123'),role='ADMIN'))
    if not User.query.filter_by(username='viewer').first(): db.session.add(User(username='viewer',password_hash=generate_password_hash('viewer123'),role='VIEWER'))
    for name,ip,kind,location in [('Local Router','192.168.1.1','ROUTER','Network room'),('Main Server','192.168.1.10','SERVER','Server room'),('Network Switch','192.168.1.2','SWITCH','Network room'),('Development PC','192.168.1.100','PC','Office'),('Access Point','192.168.1.20','ACCESS_POINT','Floor 1')]:
        if not Device.query.filter_by(name=name).first(): db.session.add(Device(name=name,ip_address=ip,device_type=kind,location=location))
    db.session.commit()
    print('Database ready. Admin: admin / admin123')
