{{- define "observantio.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "observantio.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "observantio.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "observantio.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "observantio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "observantio.selectorLabels" -}}
app.kubernetes.io/name: {{ include "observantio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "observantio.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "observantio.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "observantio.componentFullname" -}}
{{- $root := .root -}}
{{- $name := .name -}}
{{- printf "%s-%s" (include "observantio.fullname" $root) $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "observantio.secretName" -}}
{{- if .Values.secrets.existingSecretName -}}
{{- .Values.secrets.existingSecretName -}}
{{- else -}}
{{- printf "%s-secrets" (include "observantio.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "observantio.internalTLSSecretName" -}}
{{- if .Values.internalTLS.secretName -}}
{{- .Values.internalTLS.secretName -}}
{{- else -}}
{{- printf "%s-internal-tls" (include "observantio.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "observantio.postgresServiceName" -}}
{{- printf "%s-postgres" .Release.Name -}}
{{- end -}}

{{- define "observantio.redisServiceName" -}}
{{- printf "%s-redis" .Release.Name -}}
{{- end -}}

{{- define "observantio.redisPvcName" -}}
{{- printf "%s-redis-data" .Release.Name -}}
{{- end -}}

{{- define "observantio.podSecurityContextFor" -}}
{{- $root := .root -}}
{{- $component := .component | default (dict) -}}
{{- if hasKey $component "podSecurityContext" -}}
{{- toYaml ((index $component "podSecurityContext") | default (dict)) -}}
{{- else -}}
{{- toYaml ($root.Values.hardening.podSecurityContext | default (dict)) -}}
{{- end -}}
{{- end -}}

{{- define "observantio.containerSecurityContextFor" -}}
{{- $root := .root -}}
{{- $component := .component | default (dict) -}}
{{- $name := .name | default "" -}}
{{- if hasKey $component "containerSecurityContext" -}}
{{- toYaml ((index $component "containerSecurityContext") | default (dict)) -}}
{{- else if or (eq $name "postgres") (eq $name "redis") (eq $name "otlp-gateway") (eq $name "ui") (eq $name "grafana-auth-gateway") -}}
{{- toYaml (dict) -}}
{{- else -}}
{{- toYaml ($root.Values.hardening.containerSecurityContext | default (dict)) -}}
{{- end -}}
{{- end -}}
