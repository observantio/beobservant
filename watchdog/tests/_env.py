"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import os


_TEST_JWT_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDOGJi//p6Gye5Y
pEMP8f4nZVLmsUqaGC4huXMRHIFTHJ7zgWlBvF1C98GlpOkE1jkw7VF69TcAX2o/
2346A0Z1eQCwZ1iZxmokV9c7wDLJm+hW32jdL0BTgeNyBvNFz5wVeuma3fTQMoUG
fY7OSB271tZd6WhNX5oVKnXO0SZGLXVz2sDslqm3ZOci9kzFqWuWafo7KbQYVTJg
ZIMLNjIdLJMIK4A56u3ajlFPFUOfYX/epXXWdJvABi59PUsY3Aaq1MvQ7g7H+nDw
R99MdXn8pUVtk3VxXGvtCodMpuU3nnOLwFrcjRsTFfSCOKaILn6fCeQIi9AAwQXa
7dYNbJGPAgMBAAECggEAWCbGIwzlwnJZm5l6w7W2hyQ8HsdDSQDBrpQTRwThvepW
hIHcQw0t+MhfEBomvvZgFPDU8poy8dpd6D1aUrb26qUcaddyWqe225+kxH5TWs9w
Q8QgJscgpPdAERQu9rOzp65gf+ii33BUXK/Upp/K8/6Sxy1f+wRCs/3q0NC9pbLk
LNwYJ3zMMeiRaM2FSBbCENa9OBLvmXQzowRCTW/TwvFzP8vwE9xNEVeK6vT/Kx6a
VFcO0+NHoFygP2bBpwAXHG8ktKQn9bYvKCQXUj8KH9jWpAD4tA02KZnf9zFKxHgz
mj1aoo7AGjyxpq0yJnw4yqNXlq457h6LuA3FZneRzQKBgQDyTyJ7wiJPURCHlTv/
1+OJbO2WvLsO/SDg09LPHCbCQgL3P+wuBk3ODRGYy71eha0dcz4OUCXjwMMxatJO
1P4TBZtukRTG+8A3bJaxs/d4JMDKkYPDIu+882Fn/6hzPKS8IZXoSVmCa5P9I/Hm
qiEmVw31fbd2Jn15/3MBkvAkkwKBgQDZvakkVV1IVWZiZkxnHZA8u8qp2l5WToku
p/RDayqWF32NsDoZMXyq7VmKJ/RREJL6WYcl0PJ2FNb0I9jvyHhKl4ldSbQ+CnJI
GvZB3xogFRTF6/ggw8UW6jU9AijAljFwMd5Pc6+hB23WzqZOJsDTMX5wXJx2j/Fv
zkKu7FCYlQKBgQDvIhYgGTmPGau8gxVRqxhNugjIaL4bTskx2RsFdvzxXgBbTuSh
j2sd3VvudbQQItD0bZVivsqF+OkqTgf78MxGrZP2DIx6zF2o1SvreHbURUFXKUDm
RgZfbbpFztPJ1qGlYWf2dN03jz/f5aeIQ4Kvud521nlGyzmuOuKfPQpurQKBgBsa
rtlk/u2oI8yP62bSmUfWII4wLpoTwKPcKF3UE0MHvYtLqo/ERz6HuSOngZQtuf4L
8vTUI7prMa7GX5TJoZ+3aVQBfrxSVJOBN7JPcVMZDLLugr6hYAFQOjxT7nq6t4C9
1GyTfANRh2y74JvN2ybu/ExEWv2vQWCnjkl0BTxZAoGAYNPymnwNPCU1tE0BiZGA
6JZQKdwO8jp1SZSJXeopaR8blDh24ZTND8XV3mpvyMLIUFK/gGQO3klNt4Cmvh7A
ioaODoDzfGpLDHb04Iz9Oxlx+BDSDF8Cn36XXer2SNtceqaKa7AQZ3v8uXVATQ8U
cah1OO5QnUXBFLlNicryqAE=
-----END PRIVATE KEY-----
"""

_TEST_JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzhiYv/6ehsnuWKRDD/H+
J2VS5rFKmhguIblzERyBUxye84FpQbxdQvfBpaTpBNY5MO1RevU3AF9qP9t+OgNG
dXkAsGdYmcZqJFfXO8AyyZvoVt9o3S9AU4HjcgbzRc+cFXrpmt300DKFBn2Ozkgd
u9bWXeloTV+aFSp1ztEmRi11c9rA7Japt2TnIvZMxalrlmn6Oym0GFUyYGSDCzYy
HSyTCCuAOert2o5RTxVDn2F/3qV11nSbwAYufT1LGNwGqtTL0O4Ox/pw8EffTHV5
/KVFbZN1cVxr7QqHTKblN55zi8Ba3I0bExX0gjimiC5+nwnkCIvQAMEF2u3WDWyR
jwIDAQAB
-----END PUBLIC KEY-----
"""


def ensure_test_env() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql://safeuser:safePass_123@db:5432/watchdog")
    os.environ.setdefault("SKIP_STARTUP_DB_INIT", "1")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
    os.environ.setdefault("CORS_ALLOW_CREDENTIALS", "true")
    os.environ.setdefault("JWT_ALGORITHM", "RS256")
    os.environ.setdefault("JWT_PRIVATE_KEY", _TEST_JWT_PRIVATE_KEY)
    os.environ.setdefault("JWT_PUBLIC_KEY", _TEST_JWT_PUBLIC_KEY)
    os.environ.setdefault("JWT_AUTO_GENERATE_KEYS", "true")
