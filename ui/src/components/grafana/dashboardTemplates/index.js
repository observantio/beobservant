import native from "./native.json";
import linux from "./linux.json";
import windows from "./windows.json";
import docker from "./docker.json";
import postgres from "./postgres.json";
import mysql from "./mysql.json";
import gpu from "./gpu.json";
import sensors from "./sensors.json";
import nfsClient from "./nfs-client.json";

export const DASHBOARD_TEMPLATES = [
  {
    id: "native-otel-collector-overview",
    name: "OTel Collector Overview",
    icon: "monitor_heart",
    summary:
      "Single super-detailed template covering CPU, memory, disk, network, filesystem, paging, and process metrics.",
    datasourceUid: "mimir-prometheus",
    dashboard: native,
  },
  {
    id: "linux-collector-overview",
    name: "Linux Collector Overview",
    icon: "visibility",
    summary: "Grafana dashboard for Linux collector metrics using the Observantio Collector.",
    datasourceUid: "Prometheus",
    dashboard: linux,
  },
  {
    id: "windows-collector-overview",
    name: "Windows Collector Overview",
    icon: "visibility",
    summary: "Grafana dashboard for Windows collector metrics using the Observantio Collector.",
    datasourceUid: "Prometheus",
    dashboard: windows,
  },
  {
    id: "ojo-docker-containers",
    name: "Ojo — Docker & containers",
    icon: "layers",
    summary:
      "Container inventory, CPU, memory, network, block I/O, and per-container resource views from Ojo Docker metrics.",
    datasourceUid: "Prometheus",
    dashboard: docker,
  },
  {
    id: "ojo-postgresql",
    name: "Ojo — PostgreSQL",
    icon: "storage",
    summary:
      "PostgreSQL health, connections, transactions, replication lag, and query throughput from Ojo Postgres metrics.",
    datasourceUid: "Prometheus",
    dashboard: postgres,
  },
  {
    id: "ojo-mysql",
    name: "Ojo — MySQL",
    icon: "table_chart",
    summary:
      "MySQL connections, InnoDB, replication, and query performance from Ojo MySQL metrics.",
    datasourceUid: "Prometheus",
    dashboard: mysql,
  },
  {
    id: "ojo-gpu",
    name: "Ojo — GPU",
    icon: "memory",
    summary:
      "GPU utilization, memory, temperature, and power from Ojo GPU metrics.",
    datasourceUid: "Prometheus",
    dashboard: gpu,
  },
  {
    id: "ojo-hardware-sensors",
    name: "Ojo — Hardware sensors",
    icon: "device_thermostat",
    summary:
      "Temperature, fan, voltage, and other sensor readings from Ojo hardware metrics.",
    datasourceUid: "Prometheus",
    dashboard: sensors,
  },
  {
    id: "ojo-nfs-client",
    name: "Ojo — NFS client",
    icon: "folder_shared",
    summary:
      "NFS client RPC, throughput, and latency from Ojo NFS client metrics.",
    datasourceUid: "Prometheus",
    dashboard: nfsClient,
  },
];
