import os
from ollama import Client
from personalities import *
from user_stories import *
import time

# Initialize the Ollama client
client = Client(host='http://localhost:11434')

# Load the empty and filled templates from text files
with open('sick_visit_empty_template_p0.txt', 'r') as f:
    sick_visit_template_empty_0 = f.read()

with open('sick_visit_filled_template_p0.txt', 'r') as f:
    sick_visit_template_filled_0 = f.read()

with open('sick_visit_empty_template_p1.txt', 'r') as f:
    sick_visit_template_empty_1 = f.read()

with open('sick_visit_filled_template_p1.txt', 'r') as f:
    sick_visit_template_filled_1 = f.read()

with open('sick_visit_empty_template_p2.txt', 'r') as f:
    sick_visit_template_empty_2 = f.read()

with open('sick_visit_filled_template_p2.txt', 'r') as f:
    sick_visit_template_filled_2 = f.read()

with open('sick_visit_empty_template_p3.txt', 'r') as f:
    sick_visit_template_empty_3 = f.read()

with open('sick_visit_filled_template_p3.txt', 'r') as f:
    sick_visit_template_filled_3 = f.read()


def generate_filled_template_part_1(personality, template_empty, template_filled, user_input, temperature, top_k, top_p):
    """
    Generates a filled-out version of the template based on user input.

    Args:
        personality (str): The persona to use for the system message.
        template_empty (str): The empty template text with placeholders.
        template_filled (str): An example of a filled-out template.
        user_input (str): The input data to fill into the template.
        temperature (float): The temperature parameter for the model.
        top_k (int): The top_k parameter for the model.
        top_p (float): The top_p parameter for the model.

    Returns:
        str: The filled-out template.
    """
    try:
        # Define the system message
        system_message = {
            'role': 'system',
            'content': personality
        }

        # Define the user messages in a logical sequence
        user_messages = [
            {
                'role': 'user',
                'content': "Here is an empty medical visit template that needs to be filled out based on patient information:\n\n" + template_empty
            },
            {
                'role': 'user',
                'content': "Here is the transcript of the medical professional and patient interaction. You will need to look at this and find the answers to the questions:\n\n" + user_input
            },
            {
                'role': 'user',
                'content': "Here is an example of a filled out template. THIS IS ONLY AN EXAMPLE. Do not input the data from this filled out example into the final output:\n\n" + template_filled
            },
            {
                'role': 'user',
                'content': "Read the transcript while looking at the empty medical template. Use the information in the transcript to fill out the template. Do not use the example filled out template directly to fill out the form."
            },
            {
                'role': 'user',
                'content': "Only fill out the information that is required in the empty template based on the patient's responses in the transcript. Do not add extra fields."
            },
        ]

        # Combine all messages
        messages = [system_message] + user_messages

        # Send the messages to the model
        response = client.chat(
            model='phi3',
            messages=messages,
            options = {
                "temperature": temperature,
                "repeat_last_n": 200,
                "repetition_penalty": 1.3,
                "num_predict": -2,
                "top_k": top_k,
                "top_p": top_p,
                "stop": ["Extra Field:"]
            }
        )

        # Extract the filled template from the response
        filled_template = response['message']["content"].strip()
        return filled_template

    except Exception as e:
        print(f"Error generating filled template: {e}")
        return None

def save_log_output(content, user_story, personality_index, temperature, top_k, top_p, attempt):
    """
    Saves the content to a log file in the logs directory with a name that includes the parameter values,
    personality index, and attempt number.

    Args:
        content (str): The content to save.
        user_story (int): The index of the user story used.
        personality_index (int): The index of the personality used.
        temperature (float): The temperature parameter.
        top_k (int): The top_k parameter.
        top_p (float): The top_p parameter.
        attempt (int): The current attempt number.
    """
    # Format the floating-point numbers for filenames
    temp_str = f"{temperature:.2f}".replace('.', '_')
    top_p_str = f"{top_p:.2f}".replace('.', '_')

    # Create the logs directory path
    logs_dir = os.path.join('logs', f'user_story_{user_story}', f'temp_{temp_str}', f'part{personality_index}')

    # Ensure the logs directory exists
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Create a filename with parameter values and attempt number
    filename = f"attempt_{attempt}_p{personality_index}_temp{temp_str}_topk{top_k}_topp{top_p_str}.txt"
    filepath = os.path.join(logs_dir, filename)

    # Save the content to the file
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Saved log output to {filepath}")
    except Exception as e:
        print(f"Error saving log file {filepath}: {e}")

def check_outputs(response, personality, template_empty, user_input, user_story_index, personality_index, temperature, top_k, top_p, attempt=1, max_attempts=8):
    """
    Checks whether the response (filled template) correctly fills out the template
    using information from the user_input. Recursively calls itself up to max_attempts times.

    Args:
        response (str): The filled template generated by the AI.
        personality (str): The persona to use for the system message.
        template_empty (str): The empty template.
        user_input (str): The user story or input.
        user_story_index (int): The index of the user story used.
        personality_index (int): The index of the personality used.
        temperature (float): The temperature parameter.
        top_k (int): The top_k parameter.
        top_p (float): The top_p parameter.
        attempt (int): The current attempt number.
        max_attempts (int): The maximum number of verification attempts.

    Returns:
        str: The final verification result from the AI after all attempts.
    """
    try:
        print(f"Verification attempt {attempt}")

        # Define the system message
        system_message = {
            'role': 'system',
            'content': personality
        }

        # Define the user messages
        user_messages = [
            {
                'role': 'user',
                'content': "Here is the transcript of the medical professional and patient interaction:\n\n" + user_input
            },
            {
                'role': 'user',
                'content': "Here is the filled template that was generatedby the subordinate employee:\n\n" + response
            },
            {
                'role': 'user',
                'content': "Here is the empty medical visit template:\n\n" + template_empty
            },
            {
                'role': 'user',
                'content': (
                    "Please check whether the filled template was correctly filled out. "
                    "Re-read the transcript and compare the filled template with the empty template. "
                    "If the answers in the filled template match the information in the transcript, then the template is correct. "
                    "If there are any discrepancies, please correct them and provide the updated filled template."
                )
            },
        ]

        # Combine messages
        messages = [system_message] + user_messages

        # Send messages to the model
        verification_response = client.chat(
            model='phi3',
            messages=messages,
            options={
                "temperature": 0.0,
                "repeat_last_n": 200,
                "repetition_penalty": 1.3,
                "num_predict": -2,
                "stop": ["Extra Field:"]
            }
        )

        # Extract the content
        verification_content = verification_response['message']["content"].strip()

        # # Save the output to log file
        # save_log_output(
        #     content=verification_content,
        #     user_story=user_story_index,
        #     personality_index=personality_index,
        #     temperature=temperature,
        #     top_k=top_k,
        #     top_p=top_p,
        #     attempt=attempt
        # )

        # Base case: If maximum attempts reached, return the latest response
        if attempt >= max_attempts:
            return verification_content

        # Recursive case: Call the function again with the new response
        return check_outputs(
            response=verification_content,
            personality=personality,
            template_empty=template_empty,
            user_input=user_input,
            user_story_index=user_story_index,
            personality_index=personality_index,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            attempt=attempt+1,
            max_attempts=max_attempts
        )

    except Exception as e:
        print(f"Error during verification attempt {attempt}: {e}")
        return response  # Return the last response in case of error

def save_output_to_file(content, user_story, personality_index, temperature, top_k, top_p):
    """
    Saves the content to a file with a name that includes the parameter values and personality index.

    Args:
        content (str): The content to save.
        user_story (int): The index of the user story used.
        personality_index (int): The index of the personality used.
        temperature (float): The temperature parameter.
        top_k (int): The top_k parameter.
        top_p (float): The top_p parameter.
    """
    # Format the floating-point numbers for filenames
    temp_str = f"{temperature:.2f}".replace('.', '_')
    top_p_str = f"{top_p:.2f}".replace('.', '_')

    # Create the output directory path
    output_dir = os.path.join('outputs', f'user_story_{user_story}', f'temp_{temp_str}', f'part{personality_index}')

    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Create a filename with parameter values
    filename = f"output_p{personality_index}_temp{temp_str}_topk{top_k}_topp{top_p_str}.txt"
    filepath = os.path.join(output_dir, filename)

    # Save the content to the file
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Saved output to {filepath}")
    except Exception as e:
        print(f"Error saving file {filepath}: {e}")

def main():

    # Step 5: Generate and save the filled-out templates
    personas = [personality0, personality1, personality2, personality3]
    check_personas = [check_persona0, check_persona1, check_persona2, check_persona3]
    empty_templates = [sick_visit_template_empty_0, sick_visit_template_empty_1, sick_visit_template_empty_2, sick_visit_template_empty_3]
    filled_templates = [sick_visit_template_filled_0, sick_visit_template_filled_1, sick_visit_template_filled_2, sick_visit_template_filled_3]

    # Define grids for temperature, top_k, and top_p
    user_stories = [story0, story1, story2, story3, story4, story5]
    temperatures = [0.1]
    top_ks = [40]
    top_ps = [0.9]

    # Generate filled-out templates for each user story
    for user_story_index, user_input in enumerate(user_stories):
        for temperature in temperatures:
            for top_k in top_ks:
                for top_p in top_ps:
                    for idx in range(len(personas)):
                        filled_template = generate_filled_template_part_1(
                            personality=personas[idx],
                            template_empty=empty_templates[idx],
                            template_filled=filled_templates[idx],
                            user_input=user_input,
                            temperature=temperature,
                            top_k=top_k,
                            top_p=top_p
                        )
                        if filled_template:
                            # Perform recursive verification
                            manager_checked_template = check_outputs(
                                response=filled_template,
                                personality=check_personas[idx],
                                template_empty=empty_templates[idx],
                                user_input=user_input,
                                user_story_index=user_story_index,
                                personality_index=idx,
                                temperature=temperature,
                                top_k=top_k,
                                top_p=top_p,
                                attempt=1,
                                max_attempts=5
                            )

                            # Save the final filled template
                            save_output_to_file(
                                content=manager_checked_template,
                                user_story=user_story_index,
                                personality_index=idx,
                                temperature=temperature,
                                top_k=top_k,
                                top_p=top_p
                            )
                        else:
                            print(f"Failed to generate the filled-out template for Personality {idx} with Temp: {temperature}, Top_K: {top_k}, Top_P: {top_p}")
                    time.sleep(1)

if __name__ == "__main__":
    main()
