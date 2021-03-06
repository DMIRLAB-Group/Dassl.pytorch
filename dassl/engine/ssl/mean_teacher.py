import copy
from torch.nn import functional as F

from dassl.engine import TRAINER_REGISTRY, TrainerXU
from dassl.metrics import compute_accuracy
from dassl.modeling.ops.utils import ema_model_update


@TRAINER_REGISTRY.register()
class MeanTeacher(TrainerXU):
    """Mean teacher.

    https://arxiv.org/abs/1703.01780.
    """

    def __init__(self, cfg):
        super().__init__(cfg)
        self.weight_u = cfg.TRAINER.MEANTEA.WEIGHT_U
        self.ema_alpha = cfg.TRAINER.MEANTEA.EMA_ALPHA

        self.teacher = copy.deepcopy(self.model)
        self.teacher.train()
        for param in self.teacher.parameters():
            param.requires_grad_(False)

    def forward_backward(self, batch_x, batch_u):
        global_step = self.batch_idx + self.epoch * self.num_batches
        input_x, label_x, input_u = self.parse_batch_train(batch_x, batch_u)

        logit_x = self.model(input_x)
        loss_x = F.cross_entropy(logit_x, label_x)

        target_u = F.softmax(self.teacher(input_u), 1)
        prob_u = F.softmax(self.model(input_u), 1)
        loss_u = ((prob_u - target_u)**2).sum(1).mean()

        loss = loss_x + loss_u * self.weight_u
        self.model_backward_and_update(loss)

        ema_alpha = min(1 - 1 / (global_step+1), self.ema_alpha)
        ema_model_update(self.model, self.teacher, ema_alpha)

        output_dict = {
            'loss_x': loss_x.item(),
            'acc_x': compute_accuracy(logit_x.detach(), label_x)[0].item(),
            'loss_u': loss_u.item(),
            'lr': self.optim.param_groups[0]['lr']
        }

        if (self.batch_idx + 1) == self.num_batches:
            self.update_lr()

        return output_dict
