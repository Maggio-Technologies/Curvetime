# CurveTime: AI-Powered Blockchain Framework

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Paper](https://img.shields.io/badge/paper-CurveTime-red.svg)](https://www.sciencedirect.com/science/article/pii/S2665963822000495)

**CurveTime** is a production‑ready blockchain framework that **re‑purposes Proof‑of‑Work (PoW) as a reinforcement learning problem**. It seamlessly integrates blockchain consensus with distributed AI model training, turning the computational waste of traditional mining into useful AI computation.

This repository contains a complete Python implementation of the CurveTime consensus algorithm, including a Deep Q‑Network (DQN) agent, Gossip‑based P2P networking, REST/JSON‑RPC APIs, and all components needed for commercial deployment.

---

## 📜 Paper Citation

This implementation is based on the following research paper:

> **CurveTime: A blockchain framework for resource‑efficient and collaborative AI model training**  
> *Journal of Industrial Information Integration*, Volume 30, 2022, 100388  
> Available at: [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2665963822000495)

If you use this code in your research or product, please cite the original paper:

```bibtex
@article{CURVETIME2022,
  title = {CurveTime: A blockchain framework for resource‑efficient and collaborative AI model training},
  journal = {Journal of Industrial Information Integration},
  volume = {30},
  pages = {100388},
  year = {2022},
  issn = {2665-9638},
  doi = {10.1016/j.jii.2022.100388},
  url = {https://www.sciencedirect.com/science/article/pii/S2665963822000495}
}
🚀 Key Features
CurveTime Consensus – PoW transformed into a Markov Decision Process with DQN agents

Dual‑Track Computation – Blockchain validation + AI model training run in parallel

Resource Efficiency – Mining power contributes to solving real AI problems (federated learning)

Production‑Ready – REST API, JSON‑RPC, WebSocket P2P, LevelDB storage, Docker support

Extensible AI Integration – Gym environment, model versioning, distributed weight aggregation

Scalable Networking – Gossip protocol for low‑redundancy broadcast, Kademlia‑style peer discovery

🏗 Architecture
text
┌─────────────────────────────────────────────────────────┐
│               Application Layer (REST/JSON‑RPC)          │
├─────────────────────────────────────────────────────────┤
│               Service Layer (Tx/Block/Node mgmt)         │
├─────────────────────────────────────────────────────────┤
│               Core Layer (Block, UTXO, Merkle)           │
├─────────────────────────────────────────────────────────┤
│               AI Integration (DQN, Gym, Federated)       │
├─────────────────────────────────────────────────────────┤
│               Network Layer (Gossip + Peer Discovery)    │
├─────────────────────────────────────────────────────────┤
│               Storage Layer (LevelDB + PostgreSQL)       │
└─────────────────────────────────────────────────────────┘
🛠 Quick Start
Prerequisites
Python 3.11 or higher

pip & virtualenv (recommended)

Installation
bash
# Clone the repository
git clone https://github.com/yourorg/curvetime.git
cd curvetime

# Create virtual environment
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
Run a Node
bash
# Start a node with default configuration
python -m curvetime.node -c config/node.yaml
The node will start:

P2P WebSocket server on ws://0.0.0.0:9000

REST API on http://localhost:8000

JSON‑RPC on http://localhost:8545 (if enabled)

Docker Deployment
bash
docker-compose up -d
⚙️ Configuration
Edit config/node.yaml to adjust:

Section	Key	Description
node	name, address	Node identity
network	port, bootstrap_peers	P2P settings
consensus	auto_mine, dqn.*	Mining & DQN hyper‑parameters
storage	chain_db_path	LevelDB location
api	port	REST API port
rpc	enabled, port	JSON‑RPC settings
📡 API Examples
REST API (Port 8000)
bash
# Get blockchain info
curl http://localhost:8000/api/blockchain/info

# Submit a transaction
curl -X POST http://localhost:8000/api/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "pubkey1",
    "receiver": "pubkey2",
    "amount": 10.5,
    "signature": "base64sig"
  }'

# Get block by height
curl http://localhost:8000/api/block/height/42

# Start mining manually
curl -X POST http://localhost:8000/api/block/mine
JSON‑RPC (Port 8545)
bash
# Get block count
curl -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "bc_getBlockCount", "id": 1}'

# Send transaction
curl -X POST http://localhost:8545 \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "bc_sendTransaction",
    "params": [{"from": "addr1", "to": "addr2", "value": 5, "signature": "sig"}],
    "id": 2
  }'
🧠 How CurveTime Works
State representation – Each node observes blockchain state (height, mempool size, difficulty, etc.)

Action selection – DQN chooses mining strategy (transaction ordering, nonce search range, AI update inclusion)

Reward – Successful block submission yields block reward + AI contribution bonus

Parallel AI training – Nodes train the same DQN model on different data samples, then aggregate weights via federated learning

Gossip propagation – Blocks, transactions, and model updates are disseminated with probabilistic broadcast

This turns “wasted” PoW cycles into useful AI model improvement.

📂 Project Structure
text
curvetime/
├── core/            # Block, transaction, Merkle tree, blockchain
├── crypto/          # ECDSA keys, signatures, hashing
├── consensus/       # CurveTime base, DQN agent, reward model
├── network/         # P2P node, gossip protocol, peer discovery
├── storage/         # LevelDB, mempool, index
├── api/             # REST routes, middleware, JSON-RPC
├── ai_integration/  # Gym environment, trainer, model manager
├── smart_contract/  # Lightweight VM and engine
├── utils/           # Config, logging, validators
└── node.py          # Main node entry point
🔧 Development & Testing
Run unit tests:

bash
pytest tests/
Run a local multi‑node network (example script in scripts/):

bash
# Start 3 nodes with different ports
python scripts/run_cluster.py --nodes 3
📊 Performance Tuning
For production deployments, adjust:

gossip_fanout – higher = faster propagation but more bandwidth

batch_size in DQN – increase for more stable training

LevelDB cache size – set via db.write_buffer_size

Asynchronous workers – tune api concurrency with uvicorn workers

🤝 Contributing
Contributions are welcome! Please read CONTRIBUTING.md for guidelines.

📄 License
This project is licensed under the MIT License – see the LICENSE file for details.

🙏 Acknowledgements
The CurveTime authors for their innovative consensus design

OpenAI Gym for the RL environment framework

The libp2p and websockets communities for networking inspiration

Built with ❤️ for efficient, AI‑driven blockchains.
