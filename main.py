from Libraries import *

from HelperFunctions import ReturnNotes, extractModelInfo, addQuestion, importModelandTokenizer, preprocess_function,\
    preprocess_validation_examples, compute_metrics


def Pipeline(fileType, hyperparameters):
    medicalNotes = ReturnNotes(fileType)
    model_input = extractModelInfo(medicalNotes)
    model_input = addQuestion(model_input, "What is the implant maker?")

    # Convert to correct nesting
    model_input["answers"] = model_input.apply(lambda x: {"text": [x["text"]], "answer_start": [x["answer_start"]]},
                                               axis=1)

    model_input = model_input.drop(["text", "answer_start"], axis=1)

    # Feature List for dataset
    featureList = datasets.Features({'id': datasets.Value('string'),
                                     'context': datasets.Value('string'),
                                     'question': datasets.Value('string'),
                                     'answers': datasets.Sequence(feature={'text': datasets.Value(dtype='string'),
                                                                           'answer_start': datasets.Value(dtype='int32')})})


    # Convert to huggingface dataset
    tds = datasets.Dataset.from_pandas(model_input, split='train', features=featureList, preserve_index=False)
    ds = datasets.DatasetDict()
    ds['train'] = tds

    tokenizer, model = importModelandTokenizer("DistilBert")

    # The maximum length of a feature (question and context)
    max_length = hyperparameters["max_length"]
    # The authorized overlap between two part of the context when splitting
    doc_stride = hyperparameters["doc_stride"]

    # Tokenize inputs for training
    tokenized_dataset = ds.map(
        preprocess_function,
        fn_kwargs={'tokenizer': tokenizer, 'max_length': max_length, 'doc_stride': doc_stride},
        batched=True,
        remove_columns=ds["train"].column_names)
    # Convert to format useable with tensorflow
    train_set = tokenized_dataset["train"].with_format("numpy")[:]

    # Tokenize inputs for evaluation set
    validation_dataset = ds["train"].map(
        preprocess_validation_examples,
        fn_kwargs={'tokenizer': tokenizer, 'max_length': max_length, 'doc_stride': doc_stride},
        batched=True,
        remove_columns=ds['train'].column_names,
    )

    val_set = validation_dataset.remove_columns(["example_id", "offset_mapping"])
    val_set = val_set.with_format("numpy")[:]

    ## Use below if using GPU, otherwise leave commented out
    # keras.mixed_precision.set_global_policy("mixed_float16")

    optimizer = keras.optimizers.Adam(learning_rate=5e-5)
    model.compile(optimizer=optimizer)

    # model.fit(train_set, validation_data=validation_set, epochs=1)
    model.fit(train_set, epochs=hyperparameters["epochs"])

    # Get starting and ending logits
    outputs = model(val_set)
    start_logits = outputs.start_logits.numpy()
    end_logits = outputs.end_logits.numpy()

    # Evaluate test
    eval_metrics, pred_ans, act_ans = compute_metrics(start_logits, end_logits, validation_dataset, ds["train"])
    print(eval_metrics)

    # Add ground truth labels to predictions
    for i in range(len(pred_ans)):
        pred_ans[i]["actual_text"] = act_ans[i]["answers"]["text"]


    if hyperparameters["epochs"] == 1:
        outName = f'Predicted Output [New] - {hyperparameters["epochs"]} Epoch.txt'
    else:
        outName = f'Predicted Output [New] - {hyperparameters["epochs"]} Epochs.txt'

    with open(outName, 'w') as f:
        f.write(f"{eval_metrics}\n\n")
        for line in pred_ans:
            f.write(f"{line}\n")


def main():
    fileType = "smaller"
    hyperparameters = {"epochs": 1,
                       "max_length": 384,
                       "doc_stride": 128}

    Pipeline(fileType, hyperparameters)

main()