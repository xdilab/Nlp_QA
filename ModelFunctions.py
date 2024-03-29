from Libraries import *
from transformers import TFDistilBertMainLayer, TFBertMainLayer, LlamaModel
from transformers import AutoConfig, AutoModel, TFAutoModel, TFAutoModelForQuestionAnswering, TFDistilBertPreTrainedModel
from transformers.modeling_tf_utils import TFQuestionAnsweringLoss, unpack_inputs, get_initializer, input_processing, TFPreTrainedModel
from transformers.modeling_tf_outputs import TFQuestionAnsweringModelOutput
from tensorflow.keras.layers import Dense, Dropout
import sys

# Currently working on adding custom model class based on transformers
# However, currently returning much worse results despite it
# supposed to be identical copy right now...

class MyTFQuestionAnswering(TFPreTrainedModel, TFQuestionAnsweringLoss):
    def __init__(self, modelName, *inputs, **kwargs):
        # Auto functions like AutoConfig, AutoModel, etc. do not currently support Llama
        if modelName == "llama":
            self.modelName == "llama"
            modelName = r"/home/dmlee/[models]/LLaMA"
            config = LlamaConfig.from_pretrained(modelName)
        else:
            config = AutoConfig.from_pretrained(modelName)
        super().__init__(config, *inputs, **kwargs)

        if modelName == "distilbert-base-uncased-distilled-squad" \
                or modelName == "distilbert-base-cased-distilled-squad":
            self.modelName = "distilbert"
        elif modelName == "bert-base-uncased" \
                or modelName == "bert-base-cased":
            self.modelName = "bert"

        if modelName == "llama":
            self.model = LlamaModel.from_pretrained(modelName, config=config, from_pt=True)
        else:
            self.model = TFAutoModel.from_pretrained(modelName, config=config)

        self.qa_outputs = tf.keras.layers.Dense(
            config.num_labels, kernel_initializer=get_initializer(config.initializer_range), name="qa_outputs"
        )
        assert config.num_labels == 2, f"Incorrect number of labels {config.num_labels} instead of 2"

        if self.modelName == "distilbert":
            self.dropout = tf.keras.layers.Dropout(config.qa_dropout)

    @unpack_inputs
    def call(
        self,
        input_ids = None,
        attention_mask = None,
        head_mask = None,
        inputs_embeds = None,
        output_attentions = None,
        output_hidden_states = None,
        return_dict = None,
        start_positions = None,
        end_positions = None,
        training = False,
    ):
        r"""
        start_positions (`tf.Tensor` of shape `(batch_size,)`, *optional*):
            Labels for position (index) of the start of the labelled span for computing the token classification loss.
            Positions are clamped to the length of the sequence (`sequence_length`). Position outside of the sequence
            are not taken into account for computing the loss.
        end_positions (`tf.Tensor` of shape `(batch_size,)`, *optional*):
            Labels for position (index) of the end of the labelled span for computing the token classification loss.
            Positions are clamped to the length of the sequence (`sequence_length`). Position outside of the sequence
            are not taken into account for computing the loss.
        """

        model_output = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
            training=training,
        )

        hidden_states = model_output[0]  # (bs, max_query_len, dim)

        if self.modelName == "distilbert":
            hidden_states = self.dropout(hidden_states, training=training)  # (bs, max_query_len, dim)

        logits = self.qa_outputs(hidden_states)  # (bs, max_query_len, 2)
        start_logits, end_logits = tf.split(logits, 2, axis=-1)
        start_logits = tf.squeeze(start_logits, axis=-1)
        end_logits = tf.squeeze(end_logits, axis=-1)

        loss = None
        if start_positions is not None and end_positions is not None:
            labels = {"start_position": start_positions}
            labels["end_position"] = end_positions
            loss = self.hf_compute_loss(labels, (start_logits, end_logits))

        if not return_dict:
            output = (start_logits, end_logits) + model_output[1:]
            return ((loss,) + output) if loss is not None else output

        return TFQuestionAnsweringModelOutput(
            loss=loss,
            start_logits=start_logits,
            end_logits=end_logits,
            hidden_states=model_output.hidden_states,
            attentions=model_output.attentions,
        )

    # Copied from transformers.models.bert.modeling_tf_bert.TFBertForQuestionAnswering.serving_output
    def serving_output(self, output):
        hs = tf.convert_to_tensor(output.hidden_states) if self.config.output_hidden_states else None
        attns = tf.convert_to_tensor(output.attentions) if self.config.output_attentions else None

        return TFQuestionAnsweringModelOutput(
            start_logits=output.start_logits, end_logits=output.end_logits, hidden_states=hs, attentions=attns
        )