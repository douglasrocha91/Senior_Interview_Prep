# Interview Quiz — AWS & Kubernetes

Quiz de preparação baseado no mini-file-platform. Cada pergunta tem gabarito e explicação. Tente responder antes de ver a resposta.

Formato: **C** = conceitual, **P** = prático (baseado no código deste projeto), **S** = cenário / trade-off.

---

## Bloco 1 — S3

**Q1 [C]** O que diferencia object storage (S3) de um filesystem tradicional?

<details>
<summary>Gabarito</summary>

Objetos são imutáveis e endereçados por chave plana — não há diretórios reais, apenas prefixos na chave. Não há operações de append, rename ou move in-place: renomear um objeto no S3 significa copiar para nova chave e deletar a antiga. Ideal para artefatos grandes, acesso via HTTP/SDK, e durabilidade alta (11 noves) — não para arquivos que são modificados frequentemente.

</details>

---

**Q2 [P]** No projeto, o submitter-cli usa a convenção de chave `inbox/{partner}/{yyyy}/{mm}/{dd}/{transaction_id}.csv.gpg`. Por que esse formato e não simplesmente `{transaction_id}.csv.gpg`?

<details>
<summary>Gabarito</summary>

O prefixo funciona como índice. Com `inbox/acme/2026/05/` você pode listar todos os arquivos de um parceiro em um mês com `aws s3 ls --prefix inbox/acme/2026/05/` sem escanear o bucket inteiro. Em produção: auditoria por parceiro, lifecycle policies por prefixo, e troubleshooting direcionado. Chave flat forçaria scan completo para qualquer consulta.

</details>

---

**Q3 [S]** O arquivo de um parceiro foi corrompido no upload. Como você sabe que o arquivo no S3 é exatamente o que foi enviado?

<details>
<summary>Gabarito</summary>

S3 retorna um `ETag` (MD5 do conteúdo para uploads simples) no response do PUT. O cliente pode calcular o MD5 local antes do upload e comparar com o ETag retornado. Para uploads multipart o ETag tem formato diferente — nesse caso usar `--checksum-algorithm SHA256` disponível na AWS CLI v2 e boto3, que força verificação end-to-end.

</details>

---

**Q4 [C]** Qual é a diferença entre S3 Event Notifications e S3 + EventBridge?

<details>
<summary>Gabarito</summary>

Event Notifications (usado aqui) é direto: S3 chama Lambda/SQS/SNS diretamente na criação do objeto. Simples, baixa latência. EventBridge adiciona uma camada de roteamento: todos os eventos S3 vão para o EventBridge, que aplica regras de filtragem antes de rotear para N targets. Use Event Notifications para casos simples de um-para-um; EventBridge quando precisar de filtragem complexa, múltiplos targets, ou auditoria centralizada de eventos.

</details>

---

**Q5 [S]** Dois buckets foram criados: `inbound` e `results`. O entrevistador pergunta por que não usar um único bucket com prefixos diferentes. O que você responde?

<details>
<summary>Gabarito</summary>

Separação de responsabilidade e controle de acesso granular. A Lambda tem `s3:GetObject` no inbound e nada no results. O worker tem `s3:GetObject` no inbound e `s3:PutObject` no results — não pode sobrescrever arquivos originais. Com um único bucket, a policy de IAM se torna mais complexa e o risco de permissão excessiva aumenta. Também permite lifecycle policies independentes: inbound pode expirar em 30 dias, results retidos por 1 ano.

</details>

---

## Bloco 2 — SQS

**Q6 [C]** O que é Visibility Timeout e por que ele precisa ser maior que o tempo de processamento do worker?

<details>
<summary>Gabarito</summary>

Quando um consumer recebe uma mensagem, ela fica invisível para outros consumers pelo período do Visibility Timeout. Se o worker não deletar a mensagem dentro desse tempo, ela reaparece na fila como se não tivesse sido recebida. Se o timeout for menor que o tempo de processamento, a mensagem reaparece antes do worker terminar — outro worker (ou o mesmo) consome a mesma mensagem em paralelo, causando processamento duplo. Regra prática: timeout = 6× o tempo médio de processamento.

</details>

---

**Q7 [P]** No projeto, o worker usa `WaitTimeSeconds=20` no polling. O que isso significa e qual a alternativa?

<details>
<summary>Gabarito</summary>

Long polling: o worker aguarda até 20 segundos por novas mensagens antes de retornar vazio. Reduz chamadas vazias (e custo associado) e diminui latência de detecção de mensagens. A alternativa é short polling (WaitTimeSeconds=0): retorna imediatamente mesmo sem mensagens, mais chamadas, maior custo, maior latência média.

</details>

---

**Q8 [S]** Um arquivo malformado chega no sistema. A Lambda publica na fila. O worker tenta processar, falha com exception, e a mensagem retorna à fila. Isso acontece 3 vezes. O que acontece depois?

<details>
<summary>Gabarito</summary>

Após 3 recebimentos (`maxReceiveCount=3` configurado no redrive policy), SQS move a mensagem para a Dead-Letter Queue (`file-jobs-dlq`). A mensagem fica retida por 14 dias (MessageRetentionPeriod). O operador pode inspecionar via `aws sqs receive-message --queue-url $SQS_DLQ_URL`, corrigir o problema raiz, e fazer redrive (mover de volta para a fila principal) via AWS Console ou `aws sqs start-message-move-task`.

</details>

---

**Q9 [C]** SQS Standard garante "at-least-once delivery". O que isso significa na prática para o worker?

<details>
<summary>Gabarito</summary>

A mesma mensagem pode ser entregue mais de uma vez (raro, mas possível — especialmente sob alta carga ou falha de nó). O worker deve ser idempotente: processar o mesmo `transaction_id` duas vezes deve produzir o mesmo resultado sem duplicar dados. No projeto: se o worker já escreveu `results/{transaction_id}/output.csv`, a segunda execução pode checar a existência antes de reprocessar, ou simplesmente sobrescrever (resultado é o mesmo arquivo).

</details>

---

**Q10 [S]** O entrevistador pergunta: "Quando você usaria SQS FIFO ao invés de Standard?"

<details>
<summary>Gabarito</summary>

FIFO quando a ordem de processamento importa ou quando duplicatas são inaceitáveis (exactly-once). Exemplos: transações financeiras onde A deve ser processado antes de B para o mesmo cliente; sistemas de comandos onde a sequência é semântica. Trade-off: throughput limitado (3.000 mensagens/s com batching, 300 sem) vs Standard (praticamente ilimitado). Para o mini-file-platform, cada arquivo é independente — Standard é correto, mais barato e sem limitação de throughput.

</details>

---

## Bloco 3 — Lambda

**Q11 [P]** A função Lambda deste projeto recebe um evento S3. Mostre o caminho que o código percorre do evento até a publicação na SQS.

<details>
<summary>Gabarito</summary>

1. `handler(event, context)` em `handler.py` — entrypoint
2. `parse_records(event)` em `s3_event.py` — extrai lista de `S3Record` do payload
3. Para cada record: `validate_key(record.key)` em `validator.py` — regex no prefixo/extensão
4. `s3.head_object()` — busca metadados do objeto
5. `validate_metadata(metadata, transaction_id)` — confirma campos obrigatórios
6. Constrói `FileJob` com os campos normalizados
7. `publish_file_job(queue_url, job)` em `publisher.py` — serializa e chama `sqs.send_message()`

</details>

---

**Q12 [C]** O que é cold start em Lambda e quando ele importa?

<details>
<summary>Gabarito</summary>

Cold start é a latência extra da primeira invocação em um container novo — download do pacote, inicialização do runtime Python, importação dos módulos. Pode ser 100ms a 1s+. Invocações subsequentes no mesmo container são "warm" e não têm esse custo. Importa para: APIs síncronas onde o usuário aguarda resposta (ex: login), ou funções com invocação esporádica. Não importa para: pipelines assíncronos como este, onde a Lambda é disparada por evento S3 e o usuário não espera a resposta em tempo real.

</details>

---

**Q13 [S]** O entrevistador diz: "E se dois objetos chegarem no S3 ao mesmo tempo? Você teria dois workers Lambda processando em paralelo. Isso é um problema?"

<details>
<summary>Gabarito</summary>

Não é problema por design. Lambda escala horizontalmente — cada evento S3 dispara uma invocação independente. Duas invocações simultâneas processam dois objetos diferentes sem estado compartilhado entre elas. O problema surgiria se elas competissem por um recurso exclusivo — aqui não: cada invocação publica na mesma fila SQS (operação thread-safe) com `transaction_id` único. A concorrência padrão de Lambda é 1.000 invocações simultâneas por conta (configurável).

</details>

---

**Q14 [C]** Por que a Lambda execution role tem `s3:GetObject` mas não `s3:PutObject`?

<details>
<summary>Gabarito</summary>

Least privilege — a Lambda só precisa ler metadados do objeto (`head_object` é coberto por `GetObject`) para validar e rotear. Ela nunca escreve em S3. Dar `PutObject` seria permissão desnecessária: se a Lambda fosse comprometida por injeção de código no payload, um atacante não poderia sobrescrever ou adicionar objetos. Cada componente tem exatamente as permissões que usa, nada a mais.

</details>

---

**Q15 [S]** Como você faria deploy de uma atualização na Lambda sem downtime?

<details>
<summary>Gabarito</summary>

`aws lambda update-function-code` substitui o código atomicamente — invocações em andamento terminam com a versão antiga, novas invocações recebem a nova. Para controle mais fino: Lambda Versions (snapshots imutáveis) + Aliases (`prod` aponta para versão X). Canary deploy: redirecionar 10% do tráfego para versão nova via alias com pesos, monitorar CloudWatch, promover ou rollback. O script `deploy-lambda.sh` do projeto usa `update-function-code` direto — adequado para desenvolvimento, não para produção crítica.

</details>

---

## Bloco 4 — Kubernetes

**Q16 [P]** O processor-worker não tem um `Service` Kubernetes associado. Por quê?

<details>
<summary>Gabarito</summary>

O worker não recebe tráfego de entrada — ele inicia conexões de saída para SQS (polling). Um Service expõe pods para receber requisições de rede. Como o worker só consome de uma fila, não há nada para expor. Apenas a status-api precisa de Service (NodePort 30080) porque ela atende requisições HTTP externas.

</details>

---

**Q17 [C]** Qual a diferença entre `requests` e `limits` em recursos Kubernetes?

<details>
<summary>Gabarito</summary>

`requests` é o que o scheduler usa para alocar o pod em um nó — o nó precisa ter pelo menos esse recurso disponível. `limits` é o máximo que o container pode usar: ultrapassar CPU throttle (não mata o container), ultrapassar memória causa OOMKill (pod restartado). O worker usa `requests: cpu 100m / memory 128Mi` e `limits: cpu 500m / memory 256Mi` — garantido para rodar, mas pode usar mais se o nó tiver folga.

</details>

---

**Q18 [P]** Por que o Deployment usa `imagePullPolicy: Never`?

<details>
<summary>Gabarito</summary>

Em kind (Kubernetes local), as imagens não estão em um registry externo — são carregadas diretamente no nó via `kind load docker-image`. `imagePullPolicy: Never` instrui o kubelet a nunca tentar baixar a imagem de um registry, usando apenas o que está disponível localmente. Sem isso, o pod ficaria em `ImagePullBackOff` tentando baixar `mini-file-platform/processor-worker:dev` de um registry que não existe.

</details>

---

**Q19 [S]** O pod do worker está em `CrashLoopBackOff`. Qual é seu processo de diagnóstico?

<details>
<summary>Gabarito</summary>

```bash
# 1. Ver estado dos pods
kubectl get pods -n mini-file-platform

# 2. Ver eventos do pod (OOMKill, ImagePullError, etc.)
kubectl describe pod <pod-name> -n mini-file-platform

# 3. Ver logs da última execução antes do crash
kubectl logs <pod-name> -n mini-file-platform --previous

# 4. Ver logs em tempo real do restart atual
kubectl logs -f deployment/processor-worker -n mini-file-platform
```

Causas comuns: variável de ambiente faltando (KeyError), DynamoDB Local offline, credencial AWS inválida, OOMKill (aumentar memory limit). O `describe pod` mostra o exit code — exit 1 é erro de aplicação, exit 137 é OOMKill.

</details>

---

**Q20 [C]** Qual a diferença entre ConfigMap e Secret no Kubernetes? Secret é realmente seguro?

<details>
<summary>Gabarito</summary>

ConfigMap é para dados não-sensíveis (`AWS_DEFAULT_REGION`, URLs de serviços). Secret é semanticamente para dados sensíveis e é armazenado em base64 — que é encoding, não encryption. Por padrão no Kubernetes vanilla, Secrets não são cifrados em repouso (etcd os armazena em texto claro). Para segurança real: habilitar encryption at rest no etcd, ou usar um sistema externo (AWS Secrets Manager, HashiCorp Vault) com um operator que injeta valores no pod. Em produção, nunca commitar `secret.yaml` com valores reais no repositório — o projeto tem esse arquivo no `.gitignore`.

</details>

---

## Bloco 5 — AWS Cloud / IAM / Arquitetura

**Q21 [C]** O que é o princípio de least privilege e como ele está aplicado no projeto?

<details>
<summary>Gabarito</summary>

Cada componente recebe apenas as permissões que precisa para funcionar, nada mais. No projeto:
- Lambda execution role: `s3:GetObject` (inbound) + `sqs:SendMessage` (file-jobs)
- Worker (via credenciais no Secret): `s3:GetObject` (inbound) + `s3:PutObject` (results) + `sqs:ReceiveMessage` + `sqs:DeleteMessage`
- Nenhum componente tem permissões de criar/deletar recursos AWS

Se qualquer componente for comprometido, o raio de impacto é limitado ao que aquele componente pode fazer.

</details>

---

**Q22 [S]** O entrevistador pergunta: "Em produção, como você passaria as credenciais AWS para o worker no EKS, sem usar access keys?"

<details>
<summary>Gabarito</summary>

IAM Roles for Service Accounts (IRSA). No EKS, você associa uma IAM Role a uma Kubernetes Service Account. O pod que usa essa Service Account recebe credenciais temporárias via OIDC token — sem access key estático, sem secret. As credenciais são rotacionadas automaticamente. O código boto3 funciona sem alteração (usa a cadeia de credenciais padrão que inclui o metadata endpoint). No projeto local usamos Secret com access key por simplicidade — o conceito de separar permissões por Service Account é o mesmo.

</details>

---

**Q23 [S]** O que acontece se a Lambda processar o mesmo evento S3 duas vezes? (S3 pode redelivery eventos em casos raros.)

<details>
<summary>Gabarito</summary>

A Lambda publicaria dois `FileJob` com o mesmo `transaction_id` na fila SQS. O worker consumiria os dois. Para ser idempotente, o worker deveria verificar se já existe um registro com esse `transaction_id` no DynamoDB antes de processar — se existir com status `PROCESSED`, pular. No projeto atual, o worker verifica o status ao criar o registro. Uma proteção adicional seria usar `ConditionExpression` no DynamoDB para criar o item apenas se `transaction_id` não existir ainda (`attribute_not_exists`), retornando erro controlado na segunda tentativa.

</details>

---

**Q24 [C]** Qual é a diferença entre escalar horizontalmente e verticalmente? Como cada componente do projeto escala?

<details>
<summary>Gabarito</summary>

**Vertical**: aumentar o tamanho da máquina (mais CPU/RAM). Tem limite físico e causa downtime. **Horizontal**: adicionar mais instâncias. Sem limite físico teórico, zero downtime com load balancing.

No projeto:
- **Lambda**: escala horizontalmente e automaticamente — cada evento vira uma invocação independente
- **Processor-worker** (Kubernetes): escala horizontalmente aumentando `replicas` no Deployment. Múltiplos workers consumem da mesma fila SQS em paralelo sem coordenação — SQS distribui as mensagens.
- **Status-api**: escala horizontalmente atrás de um LoadBalancer Service (em produção)

</details>

---

**Q25 [S]** Descreva o fluxo completo do sistema em 60 segundos, do upload ao status `PROCESSED`.

<details>
<summary>Gabarito</summary>

1. **submitter-cli** gera um CSV de despesas, criptografa com GPG e faz upload para S3 inbound com metadados (`transaction_id`, `partner`, `schema_version`).
2. **S3** detecta o `ObjectCreated` e invoca a **Lambda** `mini-file-platform-ingest` de forma assíncrona.
3. **Lambda** valida o prefixo da chave e os metadados, constrói um `FileJob` JSON e publica no **SQS** `file-jobs`.
4. **processor-worker** (rodando no Kubernetes) faz long polling na fila, recebe o `FileJob`, e marca visibilidade do timeout.
5. Worker faz `GetObject` no S3, decripta com GPG, valida e processa o CSV linha por linha.
6. Worker grava `output.csv` e `errors.json` no S3 results, atualiza o DynamoDB com status `PROCESSED`, e deleta a mensagem da fila.
7. **status-api** expõe `GET /transactions/{id}` — retorna o estado atual do DynamoDB.

</details>

---

## Gabarito Rápido

| # | Bloco | Tipo |
|---|---|---|
| 1 | S3 | C |
| 2 | S3 | P |
| 3 | S3 | S |
| 4 | S3 | C |
| 5 | S3 | S |
| 6 | SQS | C |
| 7 | SQS | P |
| 8 | SQS | S |
| 9 | SQS | C |
| 10 | SQS | S |
| 11 | Lambda | P |
| 12 | Lambda | C |
| 13 | Lambda | S |
| 14 | Lambda | C |
| 15 | Lambda | S |
| 16 | Kubernetes | P |
| 17 | Kubernetes | C |
| 18 | Kubernetes | P |
| 19 | Kubernetes | S |
| 20 | Kubernetes | C |
| 21 | AWS/IAM | C |
| 22 | AWS/IAM | S |
| 23 | AWS/IAM | S |
| 24 | AWS/IAM | C |
| 25 | Arquitetura | S |
