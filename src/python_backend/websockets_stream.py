import tornado.httpserver
import tornado.websocket
import tornado.concurrent
import tornado.ioloop
import tornado.web
import tornado.gen
import threading
import asyncio
import socket
import numpy as np
import imutils
import copy
import time
import cv2
import os

bytes = b''

lock = threading.Lock()
connectedDevices = set()


class WSHandler(tornado.websocket.WebSocketHandler):
    def __init__(self, *args, **kwargs):
        super(WSHandler, self).__init__(*args, **kwargs)
        self.outputFrame = None
        self.frame = None
        self.id = None
        self.executor = tornado.concurrent.futures.ThreadPoolExecutor(max_workers=4)
        # self.stopEvent = threading.Event()

    def process_frames(self):
        if self.frame is None:
            return
        frame = imutils.rotate_bound(self.frame.copy(), 90)
        (flag, encodedImage) = cv2.imencode(".jpg", frame)

        # ensure the frame was successfully encoded
        if not flag:
            return
        self.outputFrame = encodedImage.tobytes()

    def open(self):
        print('new connection')
        connectedDevices.add(self)
        # self.t = threading.Thread(target=self.process_frames)
        # self.t.daemon = True
        # self.t.start()

    def on_message(self, message):
        if self.id is None:
            self.id = message
        else:
            self.frame = cv2.imdecode(np.frombuffer(
                message, dtype=np.uint8), cv2.IMREAD_COLOR)
            # self.process_frames()
            tornado.ioloop.IOLoop.current().run_in_executor(self.executor, self.process_frames)

    def on_close(self):
        print('connection closed')
        # self.stopEvent.set()
        connectedDevices.remove(self)

    def check_origin(self, origin):
        return True
    

class StreamHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, slug):
        self.set_header(
            'Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
        self.set_header('Pragma', 'no-cache')
        self.set_header(
            'Content-Type', 'multipart/x-mixed-replace;boundary=--jpgboundary')
        self.set_header('Connection', 'close')

        my_boundary = "--jpgboundary"
        client = None
        for c in connectedDevices:
            if c.id == slug:
                print(slug)
                client = c
                break
        while client is not None:
            jpgData = client.outputFrame
            if jpgData is None:
                print("empty frame")
                continue
            self.write(my_boundary)
            self.write("Content-type: image/jpeg\r\n")
            self.write("Content-length: %s\r\n\r\n" % len(jpgData))
            self.write(jpgData)
            yield self.flush()

class ButtonHandler(tornado.web.RequestHandler):
    def post(self):
        data = self.get_argument("data")
        for client in connectedDevices:
            client.write_message(data)

    def get(self):
        self.write("This is a POST-only endpoint.")


class TemplateHandler(tornado.web.RequestHandler):
    def get(self):
        deviceIds = [d.id for d in connectedDevices]
        self.render(os.path.sep.join(
            [os.path.dirname(__file__), "templates", "index.html"]), url="http://localhost:3000/video_feed/", deviceIds=deviceIds)


application = tornado.web.Application([
    (r'/video_feed/([^/]+)', StreamHandler),
    (r'/ws', WSHandler),
    (r'/button', ButtonHandler),
    (r'/', TemplateHandler),
])


if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(3000)
    myIP = socket.gethostbyname(socket.gethostname())
    print('*** Websocket Server Started at %s***' % myIP)
    tornado.ioloop.IOLoop.current().start()
