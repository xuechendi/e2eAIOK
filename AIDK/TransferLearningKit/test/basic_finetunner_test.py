#!/usr/bin/python
# -*- coding: utf-8 -*-
# @Author : Hua XiaoZhuan          
# @Time   : 8/8/2022 11:14 AM

import pytest
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),"src"))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),"test"))
import torch
import torchvision
from engine_core.finetunner.basic_finetunner import BasicFinetunner
from utils import tensor_near_equal
from copy import deepcopy

class TestBasicFinetunner:
    ''' Test BasicFinetunner

    '''
    def setup(self):
        self.pretrained_model = torchvision.models.resnet18(pretrained=True)

    def test_finetune_network(self):
        ''' test finetune_network

        :return:
        '''


        for is_frozen in [False, True]:
            target_network = torchvision.models.resnet18(pretrained=False)
            finetunner = BasicFinetunner(self.pretrained_model,is_frozen)
            ############# save old dict ##########
            old_state_dict = deepcopy(target_network.state_dict())
            ############ finetune ################
            finetunner.finetune_network(target_network)
            new_state_dict = target_network.state_dict()
            named_parameters = {name: parameter for (name, parameter) in target_network.named_parameters()}
            ################ check ###############
            for key in finetunner.finetuned_state_keys:
                if 'num_batches_tracked' in key: # statistic for bn layer, could be 0 for finetunned model
                    continue
                if type(old_state_dict[key]) is torch.Tensor:
                    assert not tensor_near_equal(old_state_dict[key], new_state_dict[key],1e-3)
                else:
                    assert old_state_dict[key] != new_state_dict[key]
                if key in named_parameters:
                    assert named_parameters[key].requires_grad == (not is_frozen)