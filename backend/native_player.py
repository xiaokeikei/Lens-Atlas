"""Qt desktop-only player; every source is an authenticated loopback media URL."""
from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QUrl


class NativePlayer(QObject):
    requested = Signal(str,str,str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dialog=None
        self.player=None
        self.state={'status':'idle'}
        self.requested.connect(self.open)

    def request(self,url,title,request_id):
        # Called by a FastAPI worker. Qt's queued signal performs all widget work on the GUI thread.
        self.requested.emit(url,title,request_id)

    def status(self):
        return dict(self.state)

    @Slot(str,str,str)
    def open(self,url,title,request_id):
        if self.dialog:
            self.dialog.close()
        self.state={'request_id':request_id,'status':'loading','frames':0,'width':0,'height':0}
        dialog=QDialog()
        self.dialog=dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle('镜迹 · 视频预览 — '+title)
        dialog.resize(1120,760)
        dialog.setStyleSheet('QDialog { background: #172e27; color: #e8eee8; } QLabel { color: #d5dfd0; } QPushButton { padding: 8px 14px; }')
        layout=QVBoxLayout(dialog)
        video=QVideoWidget(dialog)
        layout.addWidget(video,1)
        status=QLabel('正在加载原视频…',dialog)
        layout.addWidget(status)
        controls=QHBoxLayout()
        play=QPushButton('暂停',dialog)
        mute=QPushButton('开启声音',dialog)
        seek=QSlider(Qt.Orientation.Horizontal,dialog)
        seek.setRange(0,0)
        clock=QLabel('00:00 / 00:00',dialog)
        controls.addWidget(play);controls.addWidget(seek,1);controls.addWidget(clock);controls.addWidget(mute)
        layout.addLayout(controls)
        audio=QAudioOutput(dialog)
        audio.setMuted(True)
        audio.setVolume(.5)
        player=QMediaPlayer(dialog)
        self.player=player
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        def stamp(ms):
            seconds=max(0,ms//1000)
            return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}' if seconds>=3600 else f'{seconds//60:02}:{seconds%60:02}'
        def progress(position):
            if self.state.get('request_id')!=request_id:return
            if not seek.isSliderDown():seek.setValue(position)
            clock.setText(stamp(position)+' / '+stamp(player.duration()))
            self.state['position_ms']=position
        def playback(value):
            if self.state.get('request_id')!=request_id:return
            play.setText('暂停' if value==QMediaPlayer.PlaybackState.PlayingState else '播放')
        def toggle():
            if player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:player.pause()
            else:player.play()
        def toggle_mute():
            audio.setMuted(not audio.isMuted())
            mute.setText('开启声音' if audio.isMuted() else '静音')
        def frame(value):
            if self.state.get('request_id')!=request_id:return
            if value.isValid():
                self.state.update(status='video_ready',frames=self.state.get('frames',0)+1,width=value.width(),height=value.height())
                status.setText(f'{value.width()} × {value.height()} · 原生视频预览 · 未转码 · 默认静音')
        def failed(*_):
            if self.state.get('request_id')!=request_id:return
            self.state.update(status='error',error=player.errorString())
            status.setText('无法播放：'+player.errorString()+'。封面和元数据仍保留。')
        def finished(*_):
            player.stop()
            player.setSource(QUrl())
            player.setVideoOutput(None)
            player.setAudioOutput(None)
            if self.state.get('request_id')==request_id:self.state['status']='closed'
            if self.dialog is dialog:self.dialog=None;self.player=None
        player.positionChanged.connect(progress)
        player.durationChanged.connect(lambda duration:seek.setMaximum(max(0,duration)))
        player.playbackStateChanged.connect(playback)
        player.errorOccurred.connect(failed)
        video.videoSink().videoFrameChanged.connect(frame)
        seek.sliderReleased.connect(lambda:player.setPosition(seek.value()))
        play.clicked.connect(toggle);mute.clicked.connect(toggle_mute)
        dialog.finished.connect(finished)
        player.setSource(QUrl(url))
        dialog.show();dialog.raise_();dialog.activateWindow()
        player.play()

    def close(self):
        if self.dialog:self.dialog.close()
