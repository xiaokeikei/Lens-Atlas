"""Desktop settings for the explicitly enabled phone access listener."""
import secrets


def show_mobile_share_dialog(window, controller, db):
    from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QCheckBox, QLineEdit, QSpinBox, QPushButton, QLabel, QMessageBox, QApplication
    dialog = QDialog(window)
    dialog.setWindowTitle('手机访问本机图库')
    dialog.resize(520, 430)
    layout = QVBoxLayout(dialog)
    description = QLabel('手机可查看电脑当前图库与统计，并启动已有目录的只读扫描。\n原始照片、视频与相册内容不会被修改。电脑镜迹必须保持运行。')
    description.setWordWrap(True)
    layout.addWidget(description)
    enabled = QCheckBox('允许手机通过局域网 / VPN 访问')
    enabled.setChecked(bool(controller.server and controller.server.started))
    automatic = QCheckBox('下次启动镜迹时继续允许手机访问')
    automatic.setChecked(db.setting('mobile-share:auto', False))
    layout.addWidget(enabled)
    layout.addWidget(automatic)
    form = QFormLayout()
    port = QSpinBox()
    port.setRange(1024, 65535)
    port.setValue(db.setting('mobile-share:port', 52033))
    password = QLineEdit()
    password.setEchoMode(QLineEdit.EchoMode.Password)
    password.setPlaceholderText('已设置密码；留空沿用，修改密码会撤销旧会话')
    dirty = [not controller.app.state.credentials.configured()]
    if dirty[0]:
        password.setText(secrets.token_urlsafe(12))
    password.textEdited.connect(lambda _: dirty.__setitem__(0, True))
    form.addRow('访问端口', port)
    form.addRow('手机连接密码', password)
    layout.addLayout(form)
    visible = QCheckBox('显示本次填写的密码')
    visible.toggled.connect(lambda checked: password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
    layout.addWidget(visible)
    copy_password = QPushButton('复制本次连接密码')
    copy_password.clicked.connect(lambda: QApplication.clipboard().setText(password.text()) if password.text() else QMessageBox.information(dialog, '连接密码', '旧密码仅保存验证摘要，不能读取。可填写新密码后应用。'))
    layout.addWidget(copy_password)
    addresses = QLineEdit()
    addresses.setReadOnly(True)
    layout.addWidget(QLabel('手机 App：连接 → 填写下方地址和手机连接密码'))
    layout.addWidget(addresses)
    def status():
        active = bool(controller.server and controller.server.started)
        try:
            values = controller.addresses() if active else []
        except OSError:
            values = []
        addresses.setText('  或  '.join(values) if values else ('已开启，请使用电脑局域网 IP:' + str(controller.port) if active else '尚未开启手机访问'))
    status()
    copy_address = QPushButton('复制连接地址')
    def copy():
        values = controller.addresses() if controller.server and controller.server.started else []
        if values:
            QApplication.clipboard().setText(values[0])
    copy_address.clicked.connect(copy)
    layout.addWidget(copy_address)
    tip = QLabel('首次开启请保存本次连接密码。手机勾选“保持登录”后无需每次输入。\n仅提供查询和扫描任务控制，不开放目录管理或素材写入接口。')
    tip.setWordWrap(True)
    layout.addWidget(tip)
    apply = QPushButton('应用设置')
    def save():
        try:
            if dirty[0] and password.text():
                controller.app.state.credentials.set_password(password.text())
                dirty[0] = False
            if enabled.isChecked():
                if controller.port != port.value():
                    controller.stop()
                controller.start(port.value())
            else:
                controller.stop()
            db.set_setting('mobile-share:port', port.value())
            db.set_setting('mobile-share:auto', enabled.isChecked() and automatic.isChecked())
            status()
        except (ValueError, RuntimeError, OSError) as e:
            QMessageBox.warning(dialog, '手机访问未开启', str(e))
    apply.clicked.connect(save)
    layout.addWidget(apply)
    close = QPushButton('关闭设置窗口')
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()
    dialog.deleteLater()
