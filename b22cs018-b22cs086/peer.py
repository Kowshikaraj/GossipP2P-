import socket
import threading
import time
import random
import subprocess
import sys
import hashlib

# Message List (ML) as a dictionary: hash -> set of peers
ML = {}
# To track consecutive ping failures per peer
ping_failures = {}

# Dictionary to maintain active TCP connections to peers
connected_peers = {}
conn_lock = threading.Lock()

# Dictionary to maintain persistent connections to seed nodes
seed_connections = {}
seed_lock = threading.Lock()

# Dictionary to track peers we want to monitor (even if TCP connection is lost)
monitored_peers = {}
monitored_lock = threading.Lock()

# List of seed nodes as (IP, port) tuples (populated from config file)
seed_nodes = []

# Flag to ensure gossip generation starts only once
gossip_started = False
gossip_lock = threading.Lock()

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def register_with_seed(seed_ip, seed_port, my_ip, my_port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((seed_ip, seed_port))
        msg = f"REGISTER:{my_ip}:{my_port}"
        s.sendall(msg.encode())
        response = s.recv(1024).decode()
        print(f"Registration response from {seed_ip}:{seed_port}: {response}")
        with seed_lock:
            seed_connections[(seed_ip, seed_port)] = s
        threading.Thread(target=listen_to_seed, args=(s, (seed_ip, seed_port)), daemon=True).start()
        return True
    except Exception as e:
        print(f"Error registering with seed {seed_ip}:{seed_port}: {e}")
        return False

def listen_to_seed(sock, seed_addr):
    while True:
        try:
            data = sock.recv(1024).decode().strip()
            if not data:
                break
            print(f"Received from seed {seed_addr}: {data}")
        except Exception as e:
            print(f"Error communicating with seed {seed_addr}: {e}")
            break
    with seed_lock:
        if seed_addr in seed_connections:
            del seed_connections[seed_addr]
    try:
        sock.close()
    except:
        pass

def request_peer_list(seed_ip, seed_port):
    try:
        s_temp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_temp.connect((seed_ip, seed_port))
        s_temp.sendall("GET_PEER_LIST".encode())
        response = s_temp.recv(4096).decode()
        s_temp.close()
        peers = []
        if response:
            for entry in response.split(","):
                if entry:
                    ip, port_str = entry.split(":")
                    port = int(port_str)
                    peers.append((ip, port))
        return peers
    except Exception as e:
        print(f"Error requesting peer list from seed {seed_ip}:{seed_port}: {e}")
        return []

def add_monitored_peer(peer):
    with monitored_lock:
        monitored_peers[peer] = True

def connect_to_peer(peer_ip, peer_port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((peer_ip, peer_port))
        with conn_lock:
            connected_peers[(peer_ip, peer_port)] = s
        # Add to monitored peers so we keep pinging even if the TCP connection is lost.
        add_monitored_peer((peer_ip, peer_port))
        ping_failures[(peer_ip, peer_port)] = 0
        threading.Thread(target=listen_to_peer, args=(s, (peer_ip, peer_port)), daemon=True).start()
        print(f"Connected to peer {peer_ip}:{peer_port}")
        with open("outputfile.txt", "a") as f:
            f.write(f"Connected to peer {peer_ip}:{peer_port}\n")
        start_gossip_generation()
        return True
    except Exception as e:
        print(f"Error connecting to peer {peer_ip}:{peer_port}: {e}")
        return False

def listen_to_peer(sock, peer_addr):
    try:
        while True:
            data = sock.recv(1024).decode().strip()
            if not data:
                # TCP connection closed, but we still monitor the peer via ping.
                print(f"Connection closed by peer {peer_addr} (TCP closure not treated as dead)")
                break
            msg_hash = hashlib.md5(data.encode()).hexdigest()
            if msg_hash not in ML:
                ML[msg_hash] = {peer_addr}
                log = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received gossip from {peer_addr[0]}:{peer_addr[1]}: {data}"
                print(log)
                with open("outputfile.txt", "a") as f:
                    f.write(log + "\n")
                forward_gossip(data, msg_hash, exclude=peer_addr)
            elif peer_addr not in ML[msg_hash]:
                ML[msg_hash].add(peer_addr)
    except Exception as e:
        print(f"Error communicating with peer {peer_addr}: {e}")
    finally:
        with conn_lock:
            if peer_addr in connected_peers:
                del connected_peers[peer_addr]
        try:
            sock.close()
        except:
            pass

def forward_gossip(message, msg_hash=None, exclude=None):
    if msg_hash is None:
        msg_hash = hashlib.md5(message.encode()).hexdigest()
    with conn_lock:
        dead_peers = []
        for peer, sock in list(connected_peers.items()):
            if peer == exclude:
                continue
            if msg_hash in ML and peer in ML[msg_hash]:
                continue
            try:
                sock.sendall(message.encode())
                if msg_hash not in ML:
                    ML[msg_hash] = {peer}
                else:
                    ML[msg_hash].add(peer)
            except Exception as e:
                print(f"Error forwarding to {peer}: {e}")
                dead_peers.append(peer)
        for peer in dead_peers:
            if peer in connected_peers:
                try:
                    connected_peers[peer].close()
                except:
                    pass
                del connected_peers[peer]

def generate_gossip(my_ip):
    for i in range(1, 11):
        timestamp = time.time()
        msg = f"{timestamp}:{my_ip}:{i}"
        msg_hash = hashlib.md5(msg.encode()).hexdigest()
        ML[msg_hash] = set()
        log = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Generated gossip: {msg}"
        print(log)
        with open("outputfile.txt", "a") as f:
            f.write(log + "\n")
        forward_gossip(msg, msg_hash)
        time.sleep(5)

def start_gossip_generation():
    global gossip_started
    with gossip_lock:
        if not gossip_started:
            threading.Thread(target=generate_gossip, args=(get_local_ip(),), daemon=True).start()
            gossip_started = True

def ping_peer(peer_ip, peer_port):
    global ping_failures
    # Run until the peer is removed from monitored_peers (even if TCP is closed)
    while True:
        with monitored_lock:
            if (peer_ip, peer_port) not in monitored_peers:
                break
        time.sleep(13)
        try:
            if sys.platform == 'win32':
                ret = subprocess.run(["ping", "-n", "1", peer_ip],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                ret = subprocess.run(["ping", "-c", "1", peer_ip],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if ret.returncode == 0:
                print(f"Ping to {peer_ip} succeeded")
                ping_failures[(peer_ip, peer_port)] = 0
            else:
                print(f"Ping to {peer_ip} failed")
                ping_failures[(peer_ip, peer_port)] = ping_failures.get((peer_ip, peer_port), 0) + 1
        except Exception as e:
            print(f"Ping exception for {peer_ip}:{peer_port}: {e}")
            ping_failures[(peer_ip, peer_port)] = ping_failures.get((peer_ip, peer_port), 0) + 1
        
        if ping_failures[(peer_ip, peer_port)] >= 3:
            log = f"Peer {peer_ip}:{peer_port} is unreachable (3 consecutive ping failures)."
            print(log)
            with open("outputfile.txt", "a") as f:
                f.write(log + "\n")
            report_dead_node(peer_ip, peer_port)
            with monitored_lock:
                if (peer_ip, peer_port) in monitored_peers:
                    del monitored_peers[(peer_ip, peer_port)]
            break

def report_dead_node(dead_ip, dead_port):
    my_ip = get_local_ip()
    timestamp = time.time()
    msg = f"DEAD NODE:{dead_ip}:{dead_port}:{timestamp}:{my_ip}"
    print(f"Reporting dead node: {msg}")
    # Report to every seed using a fresh connection.
    for seed in seed_nodes:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(seed)
            s.sendall(msg.encode())
            ack = s.recv(1024).decode()
            print(f"Dead node reported to seed {seed}: {ack}")
            s.close()
        except Exception as e:
            print(f"Error reporting dead node to seed {seed}: {e}")

def peer_server(my_ip, my_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((my_ip, my_port))
    s.listen(5)
    print(f"Peer node listening on {my_ip}:{my_port}")
    with open("outputfile.txt", "a") as f:
        f.write(f"Peer node started on {my_ip}:{my_port}\n")
    while True:
        conn, addr = s.accept()
        print(f"Incoming connection from {addr}")
        threading.Thread(target=handle_incoming_peer, args=(conn, addr), daemon=True).start()

def handle_incoming_peer(conn, addr):
    peer_ip, peer_port = addr[0], addr[1]
    with conn_lock:
        connected_peers[(peer_ip, peer_port)] = conn
    # Add peer to monitored_peers (if not already present)
    add_monitored_peer((peer_ip, peer_port))
    ping_failures[(peer_ip, peer_port)] = 0
    print(f"Accepted connection from peer {peer_ip}:{peer_port}")
    with open("outputfile.txt", "a") as f:
        f.write(f"Accepted connection from peer {peer_ip}:{peer_port}\n")
    threading.Thread(target=ping_peer, args=(peer_ip, peer_port), daemon=True).start()
    start_gossip_generation()
    while True:
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                print(f"Connection closed by peer {peer_ip}:{peer_port} (not treated as dead)")
                break
            msg_hash = hashlib.md5(data.encode()).hexdigest()
            if msg_hash not in ML:
                ML[msg_hash] = {(peer_ip, peer_port)}
                log = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Received gossip from {peer_ip}:{peer_port}: {data}"
                print(log)
                with open("outputfile.txt", "a") as f:
                    f.write(log + "\n")
                forward_gossip(data, msg_hash, exclude=(peer_ip, peer_port))
            elif (peer_ip, peer_port) not in ML[msg_hash]:
                ML[msg_hash].add((peer_ip, peer_port))
        except Exception as e:
            print(f"Error with incoming connection from {addr}: {e}")
            break
    with conn_lock:
        if (peer_ip, peer_port) in connected_peers:
            del connected_peers[(peer_ip, peer_port)]
    try:
        conn.close()
    except:
        pass

def select_peers_power_law(all_peers, alpha=2.5):
    if not all_peers:
        return []
    n = len(all_peers)
    weights = [1.0 / ((i + 1) ** alpha) for i in range(n)]
    total = sum(weights)
    norm_weights = [w / total for w in weights]
    num_connections = max(1, min(n, int(n ** (1 / alpha))))
    print(f"Power law selection: total peers={n}, num_to_select={num_connections}")
    chosen_peers = random.choices(all_peers, weights=norm_weights, k=num_connections)
    return list(set(chosen_peers))

def main():
    global seed_nodes
    with open("outputfile.txt", "w") as f:
        f.write(f"=== Peer Node Log Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    seeds = []
    try:
        with open("config.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    ip, port_str = line.split(":")
                    port = int(port_str)
                    seeds.append((ip, port))
    except Exception as e:
        print("Error reading config file:", e)
        exit(1)
    if not seeds:
        print("No seed nodes found in config file")
        exit(1)
    seed_nodes = seeds
    n = len(seeds)
    num_to_register = (n // 2) + 1
    seeds_to_register = random.sample(seeds, num_to_register)
    my_ip = get_local_ip()
    if len(sys.argv) < 2:
        print("Usage: python peer.py <port>")
        exit(1)
    my_port = int(sys.argv[1])
    print(f"Local IP: {my_ip}, Port: {my_port}")
    print(f"Seeds to register with: {seeds_to_register}")
    with open("outputfile.txt", "a") as f:
        f.write(f"Local IP: {my_ip}, Port: {my_port}\n")
        f.write(f"Seeds to register with: {seeds_to_register}\n")
    threading.Thread(target=peer_server, args=(my_ip, my_port), daemon=True).start()
    for seed in seeds_to_register:
        if register_with_seed(seed[0], seed[1], my_ip, my_port):
            print(f"Successfully registered with seed {seed[0]}:{seed[1]}")
        else:
            print(f"Failed to register with seed {seed[0]}:{seed[1]}")
    all_peers = set()
    for seed in seeds_to_register:
        peers = request_peer_list(seed[0], seed[1])
        print(f"Got {len(peers)} peers from seed {seed[0]}:{seed[1]}")
        for p in peers:
            if p[0] == my_ip and p[1] == my_port:
                continue
            all_peers.add(p)
    all_peers = list(all_peers)
    print(f"Peer list obtained from seeds: {all_peers}")
    with open("outputfile.txt", "a") as f:
        f.write("Peer list obtained from seeds: " + str(all_peers) + "\n")
    if all_peers:
        chosen_peers = select_peers_power_law(all_peers)
        print(f"Connecting to {len(chosen_peers)} peers: {chosen_peers}")
        with open("outputfile.txt", "a") as f:
            f.write("Selected peers to connect to: " + str(chosen_peers) + "\n")
        for p in chosen_peers:
            if connect_to_peer(p[0], p[1]):
                threading.Thread(target=ping_peer, args=(p[0], p[1]), daemon=True).start()
    else:
        print("No peers available to connect.")
        with open("outputfile.txt", "a") as f:
            f.write("No peers available to connect.\n")
    start_gossip_generation()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Peer shutting down...")
        with open("outputfile.txt", "a") as f:
            f.write(f"=== Peer Node Shutting Down at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

if __name__ == '__main__':
    main()
