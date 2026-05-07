Saya ingin membuat platform orchestration untuk challenge CTF berbasis container.

Fokus utama project ini adalah membuat orchestration engine dan runtime management terlebih dahulu menggunakan CLI application sebagai interface utama. API dan web dashboard akan dibuat setelah core orchestration system sudah stabil.

Project ini bertujuan untuk menjalankan challenge CTF berbasis Docker secara otomatis, efisien, scalable, dan hemat resource.

Setiap challenge memiliki struktur seperti:

challenge/
├── Dockerfile
├── docker-compose.yml
├── challenge.yml
├── src/
├── files/
└── flag.txt

Setiap challenge dapat berupa:

* web exploitation
* pwn
* misc
* crypto
* reverse engineering
* TCP service
* HTTP service

System harus mampu:

* start challenge container
* stop challenge container
* restart/revert challenge
* auto cleanup challenge
* expose service ke internet
* generate public URL otomatis
* melakukan orchestration lifecycle challenge

Challenge source tidak disimpan manual atau upload ZIP, tetapi menggunakan Git repository sebagai source of truth.

System harus mendukung:

* GitHub repository
* GitLab repository
* Gitea repository
* repository private/public
* branch selection
* challenge path selection
* local cache challenge source
* auto sync repository
* auto pull update
* optional webhook sync

Admin cukup memasukkan:

* repository URL
* branch
* challenge path

Lalu system otomatis:

* clone repository
* cache source challenge secara lokal
* detect Dockerfile/docker-compose
* validate challenge structure
* prebuild Docker image
* save metadata challenge
* siap dijalankan kapan saja

System tidak boleh melakukan docker build setiap kali user menjalankan challenge karena startup harus cepat dan hemat resource.

Karena itu system harus memiliki:

* local challenge cache
* image prebuild system
* image reuse strategy
* build pipeline
* image tagging/versioning

Behavior utama runtime:

* challenge tidak harus dedicated per user
* challenge menggunakan shared runtime instance
* semua user dapat menggunakan challenge instance yang sama
* jika challenge belum running maka system otomatis start
* jika challenge sudah running maka semua user mendapatkan URL yang sama
* startup challenge harus cepat
* resource usage harus efisien

Lifecycle challenge:

* auto shutdown jika idle selama 15 menit
* auto destroy jika runtime melebihi batas tertentu
* restart/revert challenge memiliki cooldown minimal 5 menit
* challenge dapat direstore ke clean state
* system harus memiliki activity tracking
* system harus memiliki idle detection
* system harus memiliki health checking
* system harus memiliki runtime monitoring

Challenge exposure:

* challenge dapat di expose ke internet
* support HTTP dan TCP
* support public URL generation
* support dynamic tunnel creation
* support reverse proxy/tunneling

Tunnel system dapat menggunakan:

* FRP
* Rathole
* Cloudflare Tunnel
* ngrok
* atau alternatif lain

System juga harus mendukung:

* multiple active challenge
* automatic cleanup
* automatic tunnel cleanup
* background worker
* job queue
* event system
* runtime state management
* challenge registry
* orchestration engine

CLI menjadi interface utama untuk:

* sync challenge source
* list challenge
* build challenge
* prebuild image
* start challenge
* stop challenge
* restart challenge
* revert challenge
* cleanup challenge
* monitor runtime
* show logs
* show public URL
* inspect runtime state
* health check
* tunnel management

Saya ingin:

* architecture design
* MVP architecture
* scalable architecture
* service orchestration flow
* challenge lifecycle flow
* runtime management flow
* CLI flow
* command structure
* database schema
* challenge metadata schema
* state management strategy
* caching strategy
* build strategy
* prebuild strategy
* orchestration strategy
* tunnel/public URL strategy
* Docker orchestration recommendation
* Docker vs Kubernetes recommendation
* resource optimization strategy
* security consideration
* sandbox isolation strategy
* logging & monitoring strategy
* deployment topology
* multi-node possibility
* worker/background job architecture
* recommended programming language untuk CLI dan orchestration engine
* recommended project structure
* recommended stack untuk MVP

Saya ingin system ini scalable, modular, dan siap berkembang menjadi platform orchestration challenge CTF production-grade di masa depan.

## Orchestration Roadmap

Arsitektur MVP dan roadmap teknis ada di [docs/ctf-orchestrator-architecture.md](docs/ctf-orchestrator-architecture.md).

Kerangka control plane dan runtime manager ada di [orchestrator/](orchestrator/).
