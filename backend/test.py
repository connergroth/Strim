import redis
import os 

r = redis.from_url(os.getenv("REDIS_URL"))

print("🔎 Active Sessions:", r.keys("session:*"))
for key in r.keys("session:*"):
    print(f"Session: {key}, TTL: {r.ttl(key)} seconds")
