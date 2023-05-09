import torch
from torch import nn
from transformers import BertPreTrainedModel, BertModel
from crf import CRF
from var import id2label


class myBert(BertPreTrainedModel):
    def __init__(self, config):
        super().__init__(config)
        self.bert = BertModel(config, add_pooling_layer=False)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)

        self.trigger_embedding = nn.Embedding(num_embeddings=5, embedding_dim=2)
        # 2+768
        self.lay_norm = nn.LayerNorm(770, eps=config.layer_norm_eps)

        # self.mid_linear = nn.Sequential(
        #     nn.Linear(1024, 128),
        #     nn.ReLU(),
        #     nn.Dropout(config.hidden_dropout_prob)
        # )

        self.classifier = nn.Linear(770, len(id2label))
        self.crf = CRF(len(id2label), batch_first=True)
        self.post_init()

    def forward(self, x, trigger_position, label=None):
        # with torch.no_grad():
        bert_output = self.bert(**x)
        sequence_output = bert_output.last_hidden_state
        sequence_output = self.dropout(sequence_output)
        torch.set_printoptions(profile="full")

        trigger_position_fature = self.trigger_embedding(trigger_position)


        sequence_output = torch.cat([sequence_output, trigger_position_fature], dim=-1)
        sequence_output = self.lay_norm(sequence_output)

        # sequence_output = self.mid_linear(sequence_output)
        logits = self.classifier(sequence_output)

        # crf修正

        shift = x['attention_mask'].sum(dim=1) - x['token_type_ids'].sum(dim=1)

        re_token_type = torch.stack(
            [torch.roll(x['token_type_ids'][idx], -shift[idx].item(), 0) for idx in range(shift.size(dim=0))],
            dim=0)
        re_logits = torch.stack(
            [torch.roll(logits[idx], -shift[idx].item(), 0) for idx in range(shift.size(dim=0))],
            dim=0)

        # 计算loss
        if label is not None:

            label = torch.stack(
                [torch.roll(label[idx], -shift[idx].item(), 0) for idx in range(shift.size(dim=0))],
                dim=0)

            loss = -self.crf(emissions=re_logits, tags=label, mask=re_token_type, reduction="token_mean")
        else:
            # 这里的loss用作pred
            loss = self.crf.decode(emissions=re_logits, mask=re_token_type)
        return logits, loss


if __name__ == '__main__':
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained('./bert-base-chinese')
    model = myBert.from_pretrained('./bert-base-chinese')
    print(model)
    for idx, (name, para) in enumerate(model.named_parameters()):
        print(idx + 1, name, para.shape, para.numel())
    total = sum(p.numel() for p in model.parameters())
    print(total)


