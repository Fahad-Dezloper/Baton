// Run in the FalkorDB Browser (http://localhost:3000), graph "baton_demo", after demo/run_demo.py.

// 1. The whole picture: sessions, what they touch, what they decided, what it was based on
MATCH p = (n)-[r]->(m) RETURN p LIMIT 100;

// 2. Who is working on which file right now (live leases only)
MATCH (t:Task {status: 'claimed'})-[:TOUCHES]->(a:Artifact)
RETURN t.owner AS session, t.goal AS ticket, a.path AS file, t.lease_until AS lease_until;

// 3. Decisions about a file by anyone else (what the collision warning is built from)
MATCH (d:Decision)-[:ABOUT]->(a:Artifact {path: 'shop/db.py'})
WHERE d.status IN ['open', 'tainted']
RETURN d.author, d.kind, d.status, d.text;

// 4. Why does this decision exist? (everything it was transitively based on)
MATCH p = (d:Decision)-[:BASED_ON*1..8]->(s) WHERE d.text STARTS WITH 'endpoint reads'
RETURN p;

// 5. Blast radius of a finding: every decision derived from it, with its current status
MATCH (f:Finding)<-[:BASED_ON*1..8]-(d:Decision)
RETURN f.text AS root, f.status AS root_status, d.text AS derived, d.status AS derived_status;

// 6. Latest handoff and what it includes
MATCH (h:Handoff)-[:INCLUDES]->(x)
RETURN h.id, labels(x)[0] AS kind, coalesce(x.text, x.path, x.goal) AS item;
