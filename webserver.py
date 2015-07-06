import socket
import StringIO
import sys
import os
import time
import errno
import signal


def wait_for_child_signal(signum, frame):
    while True:
        try:
            #wait for any child process. do not block and return EWOULDBLOCK error
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError:
            return

        #no more zombie process
        if pid == 0:
            return

class WSGIServer(object):

    address_family = socket.AF_INET
    socket_type = socket.SOCK_STREAM
    request_queue_size = 20

    def __init__(self, server_address):
        # Create a listening socket
        self.listen_socket = listen_socket = socket.socket(
            self.address_family,
            self.socket_type
        )
        # Allow to reuse the same address
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_socket.bind(server_address)
        listen_socket.listen(self.request_queue_size)
        host, port = self.listen_socket.getsockname()[:2]
        self.server_name = socket.getfqdn(host)
        self.server_port = port
        self.headers_set = []

    def set_app(self, application):
        self.application = application


    def serve_forever(self):
        listen_socket = self.listen_socket
        #signal will fire when a child process exists
        signal.signal(signal.SIGCHLD, wait_for_child_signal)
        while True:
            try:
                # New client connection
                self.client_connection, client_address = listen_socket.accept()
            except IOError as e:
                code, error = e.args
                if code == errno.EINTR:
                    continue
                else:
                    raise
            pid = os.fork()
            if pid == 0:
                #close child copy
                listen_socket.close()
                # Handle one request and close the client connection. Then
                # loop over to wait for another client connection
                self.handle_one_request()
                os._exit(0)
            else:
                self.client_connection.close()

    def handle_one_request(self):
        self.request_data = request_data = self.client_connection.recv(1024)
        # Print formatted request data a la 'curl -v'
        print ''.join(
            '< {line}\n'.format(line=line)
            for line in request_data.splitlines()
            )

        self.parse_request(request_data)

        # Construct environment dictionary using request data
        env = self.get_environ()

        # It's time to call our application callable and get
        # back a result that will become HTTP response body
        result = self.application(env, self.start_response)

        # Construct a response and send it back to the client
        self.finish_response(result)

    def parse_request(self, text):
        request_line = text.splitlines()[0]
        request_line = request_line.rstrip('\r\n')
        # Break down the request line into components
        (self.request_method,  # GET
         self.path,            # /hello
         self.request_version  # HTTP/1.1
         ) = request_line.split()

    def get_environ(self):
        env = {}
        # Required WSGI variables
        env['wsgi.version'] = (1, 0)
        env['wsgi.url_scheme'] = 'http'
        env['wsgi.input'] = StringIO.StringIO(self.request_data)
        env['wsgi.errors'] = sys.stderr
        env['wsgi.multithread'] = False
        env['wsgi.multiprocess'] = False
        env['wsgi.run_once'] = False
        # Required CGI variables
        env['REQUEST_METHOD'] = self.request_method    # GET
        env['PATH_INFO'] = self.path              # /hello
        env['SERVER_NAME'] = self.server_name       # localhost
        env['SERVER_PORT'] = str(self.server_port)  # 8888
        return env

    def start_response(self, status, response_headers, exc_info=None):
        # Add necessary server headers
        server_headers = [
            ('Date', 'Tue, 2nd July 2015 12:54:48 GMT'),
            ('Server', 'WSGIServer 0.2'),
        ]
        self.headers_set = [status, response_headers + server_headers]

    def finish_response(self, result):
        try:
            status, response_headers = self.headers_set
            response = 'HTTP/1.1 {status}\r\n'.format(status=status)
            for header in response_headers:
                response += '{0}: {1}\r\n'.format(*header)
            response += '\r\n'
            for data in result:
                response += data

            print ''.join(
                '> {line}\n'.format(line=line)
                for line in response.splitlines()
                )
            self.client_connection.sendall(response)
            time.sleep(30)
        finally:
            self.client_connection.close()


SERVER_ADDRESS = (HOST, PORT) = '', 5000


def make_server(server_address, application):
    server = WSGIServer(server_address)
    server.set_app(application)
    return server


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Provide a WSGI application object as module:callable')
    app_path = sys.argv[1]
    module, application = app_path.split(':')
    module = __import__(module)
    application = getattr(module, application)
    httpd = make_server(SERVER_ADDRESS, application)
    print 'WSGIServer: Serving HTTP on port {port} ...\n'.format(port=PORT)
    httpd.serve_forever()
