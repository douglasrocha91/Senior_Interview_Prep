# AWS & Kubernetes — Interview Fluency Guide

Talking points ancorados no código deste projeto. Para cada serviço: o que é, como está implementado aqui, conceitos que o entrevistador espera, e Q&A direto.

Pronto para praticar? → [interview-quiz.md](interview-quiz.md) — 25 perguntas com gabarito.

---

## 1. AWS Cloud — Visão Geral

### O que é

AWS é um conjunto de serviços de infraestrutura gerenciada acessados via API. Você não gerencia servidores físicos — você declara recursos (buckets, filas, funções) e a AWS cuida de disponibilidade, replicação e hardware.

### Como está no projeto

O mini-file-platform usa três serviços gerenciados da AWS: S3 (armazenamento), SQS (fila), e Lambda (compute serverless). As credenciais ficam no `.env` e são injetadas no cluster via `Secret` do Kubernetes — nunca hard-coded no código.

**Provisionamento:** `infra/aws/bootstrap.sh` — cria buckets, filas e DLQ via AWS CLI. O script é idempotente: verifica se o recurso existe antes de criar.

### Conceitos que o entrevistador espera

| Conceito | Definição rápida |
|---|---|
| **IAM** | Identity and Access Management — controla quem pode fazer o quê. Cada Lambda tem uma execution role com permissões mínimas (least privilege). |
| **Region / AZ** | Region = datacenter geográfico (ex: `us-east-1`). AZ = zona de disponibilidade dentro da região. SQS e S3 são regionais. |
| **ARN** | Amazon Resource Name — identificador único de qualquer recurso AWS. Usado no redrive policy da DLQ. |
| **SDK / boto3** | Biblioteca Python que traduz chamadas locais em chamadas HTTP para a API da AWS. |

### Q&A típico

**"Como você gerencia credenciais AWS em produção?"**
> Nunca em código ou variável de ambiente hardcoded. Em produção: IAM Roles attached a EC2/ECS/EKS — a instância recebe credenciais temporárias via metadata endpoint, sem secret key. No projeto local usamos `.env` + Kubernetes `Secret` para simular isso de forma segura.

**"O que é least privilege em IAM?"**
> Cada componente tem apenas as permissões que precisa. A Lambda execution role (`mini-file-platform-lambda-role`) tem `s3:GetObject` e `sqs:SendMessage` — não tem permissão de escrever em S3 nem ler da fila. O worker tem permissões separadas para ler da fila e escrever nos resultados.

---

## 2. S3 — Object Storage e Event Notifications

### O que é

S3 é armazenamento de objetos — arquivos imutáveis endereçados por `bucket/key`. Não é um filesystem; não há diretórios reais, apenas prefixos na chave. Durabilidade de 11 noves (99.999999999%).

### Como está no projeto

Dois buckets:
- `mini-file-platform-inbound` — recebe arquivos criptografados (`.csv.gpg`) do submitter-cli
- `mini-file-platform-results` — recebe output.csv e errors.json após processamento

**Convenção de chave:** `inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg`  
Isso permite listagem por parceiro/data sem scan completo — prefixo funciona como índice.

**Event Notifications:** o bucket inbound está configurado para disparar a Lambda em qualquer `s3:ObjectCreated:*`. Isso está em `infra/aws/wire-s3-notification.sh` e é o gatilho central do pipeline.

**Upload com metadata:** `submitter-cli/app/uploader.py` adiciona `x-amz-meta-partner`, `x-amz-meta-transaction_id`, e `x-amz-meta-schema_version` ao objeto. A Lambda lê esses metadados via `s3.head_object()` em `ingest-lambda/app/handler.py:58`.

### Conceitos que o entrevistador espera

| Conceito | Definição rápida |
|---|---|
| **Presigned URL** | URL temporária que permite upload/download direto sem expor credenciais. Usado em padrões de upload seguro do cliente. |
| **Event Notification** | S3 chama Lambda, SQS ou SNS quando um objeto é criado/deletado. Trigger assíncrono — S3 não espera a Lambda terminar. |
| **Versioning** | S3 pode manter múltiplas versões do mesmo objeto. Não ativamos aqui para manter simplicidade. |
| **Storage Classes** | Standard (acesso frequente), Infrequent Access, Glacier (archiving). Relevante para custo em produção. |
| **Public access block** | Todos os buckets no projeto têm `BlockPublicAcls=true` — nenhum objeto é público. |

### Q&A típico

**"S3 é consistente?"**
> Desde 2020, S3 oferece strong read-after-write consistency para PUTs e DELETEs. Um objeto escrito imediatamente está disponível para leitura — sem janela de inconsistência eventual.

**"Como a Lambda sabe de qual bucket foi chamada?"**
> O evento S3 contém o objeto completo: `event["Records"][0]["s3"]["bucket"]["name"]` e `event["Records"][0]["s3"]["object"]["key"]`. Veja `ingest-lambda/app/s3_event.py` — `S3Record` encapsula exatamente esses campos.

**"Por que dois buckets ao invés de um?"**
> Separação de responsabilidade e controle de acesso mais fino. O worker tem permissão de leitura no inbound e escrita no results — nunca pode sobrescrever um arquivo original. Também facilita policies diferentes de lifecycle (inbound pode expirar em 30 dias, results podem ser retidos mais).

---

## 3. SQS — Queue-Based Decoupling

### O que é

SQS é uma fila de mensagens gerenciada. Produtores publicam mensagens, consumidores fazem polling e processam. A fila desacopla produção de consumo — o producer não sabe quem vai consumir, e o consumer não sabe quem produziu.

### Como está no projeto

**Fluxo:** Lambda publica `FileJob` na fila `file-jobs` → processor-worker faz long polling e consome.

**Publisher:** `ingest-lambda/app/publisher.py` — chama `sqs.send_message()` com o corpo serializado como JSON.

**Consumer:** `processor-worker/app/consumer.py` — long polling com `WaitTimeSeconds=20`. Só deleta a mensagem (`sqs.delete_message()`) após processamento bem-sucedido. Se o worker falha, a mensagem retorna à fila depois do `VisibilityTimeout`.

**DLQ:** `file-jobs-dlq` com `maxReceiveCount=3`. Após 3 tentativas fracassadas, a mensagem vai para a DLQ — poison message isolado sem travar a fila principal.

### Conceitos que o entrevistador espera

| Conceito | Definição rápida |
|---|---|
| **Visibility Timeout** | Período em que uma mensagem está "invisível" para outros consumers após ser recebida. Deve ser maior que o tempo de processamento. Aqui: 30s. |
| **Long Polling** | Consumer espera até 20s por novas mensagens antes de retornar vazio. Reduz chamadas vazias e latência comparado ao short polling. |
| **Dead-Letter Queue (DLQ)** | Fila separada para mensagens que falharam N vezes. Evita que uma mensagem defeituosa bloqueie a fila principal indefinidamente. |
| **At-least-once delivery** | SQS garante entrega pelo menos uma vez — pode duplicar. O worker deve ser idempotente (processar o mesmo `transaction_id` duas vezes não deve duplicar resultado). |
| **FIFO vs Standard** | Standard: alta throughput, sem ordem garantida, possível duplicata. FIFO: ordem garantida, exatamente uma vez, menor throughput. Usamos Standard. |

### Q&A típico

**"Por que deletar a mensagem só depois de processar com sucesso?"**
> Se o worker falha no meio do processamento e já deletou a mensagem, o arquivo fica em estado inconsistente sem possibilidade de retry. Ao deletar somente após sucesso, o `VisibilityTimeout` expira e a mensagem retorna à fila para nova tentativa — garantindo at-least-once processing.

**"Como você inspeciona a DLQ?"**
> `aws sqs receive-message --queue-url $SQS_DLQ_URL --max-number-of-messages 10`. Ver `docs/failure-scenarios.md` para o procedimento de redrive (mover mensagem da DLQ de volta para a fila principal para reprocessamento).

**"O que acontece se dois workers consumirem a mesma mensagem ao mesmo tempo?"**
> SQS torna a mensagem invisível para outros consumers durante o `VisibilityTimeout` depois que um consumer a recebe. Dois workers não processam a mesma mensagem simultaneamente — mas após o timeout a mensagem reaparece se o primeiro worker não deletou. Por isso idempotência no worker é importante.

---

## 4. Lambda — Serverless Compute

### O que é

Lambda é compute event-driven sem servidor para gerenciar. Você sobe um zip com o código, define o handler, e a AWS executa quando o trigger dispara. Escala automaticamente — cada invocação é independente.

### Como está no projeto

**Handler:** `ingest-lambda/app/handler.py` — função `handler(event, context)`. Recebe o evento S3, valida o objeto, e publica na SQS.

**Trigger:** S3 `ObjectCreated` no bucket inbound — configurado em `infra/aws/wire-s3-notification.sh`.

**Deploy:** `infra/aws/deploy-lambda.sh` — empacota `ingest-lambda/app/` + `shared/` em um zip e faz `aws lambda create-function` ou `update-function-code`.

**Execution Role:** IAM role com permissões mínimas — `s3:GetObject` (para `head_object`) e `sqs:SendMessage`. Criada no mesmo script de deploy.

**Variáveis de ambiente:** `SQS_FILE_JOBS_URL` injetada na função — nunca hardcoded. Lida via `os.environ["SQS_FILE_JOBS_URL"]`.

### Conceitos que o entrevistador espera

| Conceito | Definição rápida |
|---|---|
| **Cold start** | Primeira invocação inicializa o container — latência extra (~100ms–1s). Invocações subsequentes reutilizam o container (warm). Para workloads de ingestion assíncrona como aqui, cold start não é problema. |
| **Timeout** | Tempo máximo de execução — padrão 3s, máximo 15min. Lambda deve ser rápida e focada. |
| **Concurrency** | Lambda escala horizontalmente — cada objeto S3 disparado gera uma invocação independente. Sem state compartilhado entre invocações. |
| **Execution role** | IAM role que a função assume durante a execução. Define o que ela pode fazer na AWS. |
| **Idempotência** | Se S3 disparar o mesmo evento duas vezes (pode acontecer), publicar o mesmo `FileJob` duas vezes na fila. O worker deve lidar com isso via `transaction_id` único. |

### Q&A típico

**"Por que Lambda aqui e não outro serviço?"**
> A Lambda é o ponto de entrada do sistema — recebe o evento S3, valida o objeto, e delega o trabalho pesado para o worker. É exatamente o caso de uso ideal: execução curta, event-driven, sem estado. Um container longo para esse papel seria desperdício — ficaria ocioso esperando eventos.

**"Como você empacota dependências para Lambda?"**
> Duas opções: (1) incluir `site-packages` no zip junto com o código, ou (2) usar Lambda Layers para dependências compartilhadas. Aqui usamos a abordagem simples do zip — `shared/` é copiado junto com `ingest-lambda/app/`. Para produção com dependências pesadas, Layer é melhor.

**"O que acontece se a Lambda falhar?"**
> Com trigger S3, falhas são retentadas automaticamente pelo S3 (2 tentativas adicionais com backoff). Se todas falharem, S3 pode enviar para uma destination (SQS ou SNS) configurada na função. Sem retry infinito — arquivos defeituosos ou malformados devem ser capturados na validação e retornados como `skipped`, não como exception.

---

## 5. Kubernetes — Container Orchestration

### O que é

Kubernetes orquestra containers — decide onde rodar, reinicia em caso de falha, injeta configuração, e gerencia o ciclo de vida de pods. Você declara o estado desejado (1 replica do worker), e o control plane trabalha para manter isso.

### Como está no projeto

Dois serviços rodando em kind (Kubernetes local):
- `processor-worker` — Deployment com 1 réplica, sem Service (não recebe tráfego externo, só consome SQS)
- `status-api` — Deployment com 1 réplica + Service NodePort na porta 30080

**Configuração:** `ConfigMap` para variáveis não-sensíveis (`AWS_DEFAULT_REGION`, `DYNAMODB_URL`, etc.) e `Secret` para credenciais AWS. Ambos injetados via `envFrom` no Deployment — o container recebe como variáveis de ambiente.

**Build e deploy local:**
```
docker build → kind load docker-image → kubectl apply -f infra/kubernetes/
```

`imagePullPolicy: Never` — Kubernetes não tenta baixar a imagem de um registry, usa a imagem carregada localmente.

### Conceitos que o entrevistador espera

| Conceito | Definição rápida |
|---|---|
| **Pod** | Menor unidade deployável — um ou mais containers com rede e storage compartilhados. |
| **Deployment** | Gerencia réplicas de pods. Define a spec do pod, quantas réplicas, e a estratégia de rollout. |
| **Service** | Expõe um conjunto de pods como endpoint estável. NodePort expõe no host (porta 30080 aqui). |
| **ConfigMap / Secret** | Armazenam configuração separada do código. ConfigMap para não-sensíveis, Secret para credenciais (base64 encoded). |
| **Namespace** | Agrupamento lógico de recursos. Projeto usa `mini-file-platform` para isolar do `default`. |
| **Resource requests/limits** | `requests` = garantido para scheduling, `limits` = máximo antes de OOMKill ou throttle. Worker: 100m CPU / 128Mi garantidos, 500m / 256Mi máximo. |

### Q&A típico

**"Por que Kubernetes para o worker e não só rodar local direto?"**
> Kubernetes replica o ambiente de produção — injeta config via ConfigMap/Secret da mesma forma que EKS faria, gerencia restarts automaticamente, e permite demonstrar `kubectl logs`, `kubectl describe pod`, e troubleshooting de deployment. Rodar direto mascara esse nível de integração.

**"Como você inspeciona o que está rodando?"**
```bash
kubectl get pods -n mini-file-platform
kubectl logs -f deployment/processor-worker -n mini-file-platform
kubectl describe pod <pod-name> -n mini-file-platform
```

**"O que acontece se o worker crashar?"**
> O Deployment tem `restartPolicy: Always` por padrão. O kubelet reinicia o container automaticamente. O número de restarts fica visível em `kubectl get pods` — um worker com múltiplos restarts indica problema no processamento (ex: credencial errada, DynamoDB Local offline).

**"Diferença entre ConfigMap e Secret?"**
> Ambos injetam configuração no pod. A diferença é semântica e de controle de acesso: Secret é base64-encoded (não é encryption) mas o Kubernetes pode ser configurado para criptografar Secrets at rest e aplicar RBAC mais restrito. Em produção, Secrets são gerenciados por um vault externo (AWS Secrets Manager, Vault) — nunca commitados no repositório. Veja: `infra/kubernetes/secret.yaml` está no `.gitignore`.

---

## Script de Walkthrough (5 minutos)

Use este roteiro para demonstrar o sistema ao vivo:

```
1. "O pipeline começa com o submitter-cli que gera e criptografa um CSV."
   → make submit-generate-and-submit PARTNER=acme ROWS=10

2. "O arquivo vai para o S3 inbound. O S3 dispara a Lambda automaticamente."
   → aws s3api head-object --bucket mini-file-platform-inbound --key inbox/acme/...

3. "A Lambda valida o objeto e publica um FileJob na fila SQS."
   → aws sqs get-queue-attributes --queue-url $SQS_FILE_JOBS_URL --attribute-names ApproximateNumberOfMessages

4. "O processor-worker no Kubernetes consome a mensagem, decripta, processa, e grava no DynamoDB e S3."
   → kubectl logs -f deployment/processor-worker -n mini-file-platform

5. "A status-api expõe o estado da transação."
   → curl http://localhost:8080/transactions/<transaction_id>
```
