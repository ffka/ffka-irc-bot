CREATE TABLE "nodes_copy" (
        node_id VARCHAR NOT NULL, 
        mac VARCHAR, 
        hostname VARCHAR, 
        lat FLOAT, 
        lon FLOAT, 
        hardware VARCHAR, 
        contact VARCHAR, 
        autoupdate BOOLEAN, 
        branch VARCHAR, 
        firmware_base VARCHAR, 
        firmware_release VARCHAR, 
        firstseen DATETIME, 
        lastseen DATETIME, 
        online BOOLEAN, 
        gateway BOOLEAN, 
        clientcount INTEGER, 
        source VARCHAR,
        PRIMARY KEY (node_id), 
        CHECK (autoupdate IN (0, 1)), 
        CHECK (online IN (0, 1)), 
        CHECK (gateway IN (0, 1))
);

INSERT INTO nodes_copy (node_id, mac, hostname, lat, lon, hardware, contact, autoupdate, branch, firmware_base, firmware_release, firstseen, lastseen, online, gateway, clientcount, 'alfred.json')
SELECT node_id, mac, hostname, lat, lon, hardware, contact, autoupdate, branch, firmware_base, firmware_release, firstseen, lastseen, online, gateway, clientcount FROM nodes;

DROP TABLE nodes;

ALTER TABLE nodes_copy RENAME TO nodes;