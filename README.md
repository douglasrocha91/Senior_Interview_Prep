# Senior Interview Prep

Reference guide for interview preparation — job description, key technologies, and study materials.

---

## Target Position

**Integration File Management — SAP Concur (Travel & Expense)**

---

## The Team

The **Integration File Management Team** manages over **150,000 daily file uploads** across three regions:

| Region | Coverage |
|---|---|
| North America | US |
| Europe | Prague |
| Asia-Pacific | — |
| South America | Brazil |

Every file category is a critical input to integrations that power the SAP Concur Travel & Expense product. The team's priorities are **data integrity** and **adherence to service level agreements (SLAs)**.

---

## Responsibilities

| Area | Description |
|---|---|
| File traffic management | Own inbound, high-volume file pipelines for SAP Concur T&E products |
| Queue-based workflows | Develop file transaction and queue-driven processing systems |
| Internal platform services | Build new file transaction services consumed by other R&D teams |
| Troubleshooting | Fast diagnosis and recovery under production pressure |
| Initiative management | Manage and prioritize multiple concurrent projects |
| Compliance & security | Incorporate compliance and security requirements into every design decision |
| Proactive problem-solving | Identify and resolve issues before they escalate |
| Agile collaboration | Work closely with development peers and implementation teams |

---

## Required Skills

### Python
- Production-level Python software development
- Solid grasp of **object-oriented programming**
- Know when a simple script is more appropriate than a full OOP solution

### AWS Cloud
- **Kubernetes** — container orchestration
- **S3** — object storage, event notifications
- **SQS** — queue-based decoupling and message processing
- **Lambda** — serverless compute and event-driven functions

### Cryptography
- **PGP** encrypt/decrypt workflows
- Familiarity with **GnuPG (GPG)**

### Engineering practices
- Continuous Integration (CI)
- Automated deployments (CD)

### Communication
- Fluent English required — team spans Prague, Brazil, and the US

---

## Key Study Areas

> Sections to focus on for technical preparation.

- [ ] AWS: S3 event triggers → SQS → Lambda pipeline patterns
- [ ] AWS: Kubernetes on EKS — deployments, services, config maps
- [ ] Python: OOP design patterns vs. scripting trade-offs
- [ ] GPG: key management, batch encryption/decryption, GnuPG CLI
- [ ] SLA concepts: retry strategies, dead-letter queues, alerting
- [ ] Agile: ceremonies, working with cross-functional teams across time zones
- [ ] Security: least-privilege IAM, encryption at rest and in transit

---

## Repository Structure

```
Senior_Interview_Prep/
└── mini-file-platform/     # Hands-on lab: file upload platform (S3, Lambda, SQS, GPG)
```
