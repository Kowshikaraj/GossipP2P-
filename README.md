# Gossip Protocol over a Peer-to-Peer Network

## Overview

This project implements a gossip protocol over a peer-to-peer (P2P) network. The system consists of two types of nodes:

- **Seed Nodes (seed.py):**  
  These nodes act as bootstrap points for new peers. They register incoming peers, maintain a list of active peers, and process dead node notifications.

- **Peer Nodes (peer.py):**  
  Peers register with one or more seed nodes to join the network, query for a list of peers, and then select a subset of peers to connect with based on a power-law selection mechanism. Each peer generates gossip messages, forwards them to its connected neighbors, and continuously checks the liveness of peers using ICMP ping. If a peer fails three consecutive pings, it is reported as dead to the seed nodes.

## File Descriptions

- **seed.py:**  
  Implements seed node functionality. It listens for TCP connections from peers, handles registration (`REGISTER`), serves peer list requests (`GET_PEER_LIST`), and removes dead nodes when notified (`DEAD NODE`).

- **peer.py:**  
  Implements peer node functionality. It registers with seed nodes, retrieves the list of peers, selects a subset based on a power-law algorithm, establishes connections, generates gossip messages, forwards messages, and monitors the liveness of peers using periodic ICMP ping. A peer reports a dead node to seeds using a fresh connection if three consecutive pings fail.

- **config.txt:**  
  Contains a list of seed nodes. Each line is in the format:
  ```
  IP:Port
  ```
  For example:
  ```
  172.31.79.63:5000
  172.31.77.178:5000
  ```

- **outputfile.txt:**  
  A log file where both seed and peer nodes write events and messages for debugging and review.

- **README.md:**  
  This file, which provides an overview and instructions on compiling and running the project.

## Requirements

- Python 3.x  
- No external libraries are required; the code uses Python’s standard libraries:
  - socket, threading, time, random, subprocess, sys, hashlib

## Running the Code

### 1. Configure the Network

- Edit `config.txt` to include the IP addresses and port numbers of your seed nodes, one per line. For example:
  ```
  172.31.79.63:5000
  172.31.77.178:5000
  ```

### 2. Start Seed Nodes

- Open a terminal (or Command Prompt).
- Navigate to the project directory.
- Start a seed node by running:
  ```bash
  python seed.py 5000
  ```
- You can run multiple seed nodes on different ports (and/or on different machines) by repeating the above step with different port numbers.

### 3. Start Peer Nodes

- Open another terminal.
- Navigate to the project directory.
- Run a peer node by specifying a port number, for example:
  ```bash
  python peer.py 6000
  ```
- To simulate a network, open additional terminals and run `peer.py` with different port numbers (e.g., 6001, 6002, etc.).

### 4. Observing the Network Behavior

- **Registration:**  
  Each peer registers with at least ⌊n/2⌋ + 1 seed nodes (where n is the number of seeds). Registration details are printed to the console and logged in `outputfile.txt`.

- **Peer List and Power-Law Selection:**  
  Peers query the seeds for a list of available peers. Using a power-law based selection mechanism, each peer computes weights (using a function like `1/(i+1)^α` with α typically set to 2.5) for the peers in the list, normalizes them, and randomly selects a small number of peers to connect with.

- **Gossip Protocol:**  
  Once connections are established, peers generate gossip messages (in the format `<timestamp>:<IP>:<Msg#>`) every 5 seconds (up to 10 messages). Gossip messages are forwarded to all connected peers. Both sent and received messages are logged.

- **Liveness Checking (Ping):**  
  Each peer continuously pings every monitored peer (even if the TCP connection is closed) every 13 seconds. If three consecutive ping failures occur for a peer, it is deemed unreachable, and a dead node message is reported to the seed nodes via a fresh TCP connection.

## Troubleshooting

- **ICMP/Ping Issues:**  
  On some systems (especially Windows), the firewall may block ICMP echo requests (ping). To allow pings on Windows, open an Administrator Command Prompt and run:
  ```
  netsh advfirewall firewall add rule name="Allow ICMPv4-In" protocol=icmpv4:8,any dir=in action=allow
  ```
- **Testing on a Single Machine:**  
  When simulating on a single machine, be aware that network caching (ARP caching) or firewall settings may affect ping responses. For accurate results, consider testing on separate machines or adjust your settings accordingly.

## Summary

This project demonstrates a P2P gossip protocol with:
- Seed nodes that register and manage peer lists.
- Peer nodes that select a subset of peers to connect to using a power-law distribution.
- A gossip mechanism that ensures each message is forwarded only once per connection.
- A liveness check using periodic ICMP ping, with dead node reporting when a peer fails three consecutive pings.

Follow the steps above to compile and run the code, and refer to `outputfile.txt` for detailed logs of network activity.
