# \# Zabbix Report Exporter

# 

# Aplikasi internal untuk mengambil data monitoring dari Zabbix,

# menghasilkan laporan PDF, dan menjalankan laporan terjadwal.

# 

# \## Arsitektur

# 

# ```text

# Client LAN

# &#x20;   |

# &#x20;   v

# Nginx :8080

# &#x20;   |

# &#x20;   +--> Frontend :3000

# &#x20;   |

# &#x20;   +--> Backend :8000

# &#x20;            |

# &#x20;            +--> Zabbix API

# &#x20;            +--> PostgreSQL

# &#x20;            +--> Redis

# 

# Worker

# &#x20;   |

# &#x20;   +--> Scheduler

# &#x20;   +--> Zabbix API

# &#x20;   +--> PDF Generator

# &#x20;   +--> PostgreSQL

