import socket
import threading
import time

# Global peer list (as a set of (IP, port) tuples)
peer_list = set()
lock = threading.Lock()

def handle_client(conn, addr):
    try:
        data = conn.recv(1024).decode().strip()
        if not data:
            return
        print(f"Received from {addr}: {data}")
        
        if data.startswith("REGISTER"):
            parts = data.split(":")
            if len(parts) >= 3:
                peer_ip = parts[1]
                peer_port = int(parts[2])
                with lock:
                    peer_list.add((peer_ip, peer_port))
                response = "Registered"
                conn.sendall(response.encode())
                with open("outputfile.txt", "a") as f:
                    f.write(f"Registered peer {peer_ip}:{peer_port}\n")
            else:
                conn.sendall("Invalid REGISTER format".encode())
        elif data.startswith("GET_PEER_LIST"):
            with lock:
                peers = list(peer_list)
            response = ",".join([f"{ip}:{port}" for ip, port in peers])
            conn.sendall(response.encode())
            with open("outputfile.txt", "a") as f:
                f.write("Sent peer list: " + response + "\n")
        elif data.startswith("DEAD NODE"):
            parts = data.split(":")
            if len(parts) >= 5:
                dead_ip = parts[1]
                dead_port = int(parts[2])
                with lock:
                    if (dead_ip, dead_port) in peer_list:
                        peer_list.remove((dead_ip, dead_port))
                        print(f"Removed dead peer {dead_ip}:{dead_port}")
                        with open("outputfile.txt", "a") as f:
                            f.write(f"Removed dead peer {dead_ip}:{dead_port}\n")
            conn.sendall("ACK".encode())
        else:
            conn.sendall("Unknown command".encode())
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

def start_server(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', port))
    s.listen(5)
    print(f"Seed node listening on port {port}")
    
    with open("outputfile.txt", "w") as f:
        f.write(f"=== Seed Node Log Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        f.write(f"Seed node started on port {port}\n")
    
    while True:
        conn, addr = s.accept()
        client_thread = threading.Thread(target=handle_client, args=(conn, addr))
        client_thread.daemon = True
        client_thread.start()

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python seed.py <port>")
        exit(1)
    port = int(sys.argv[1])
    start_server(port)
